# -*- coding: utf-8 -*-

from trac.core import *
from trac.resource import Resource, ResourceNotFound
from trac.mimeview.api import Mimeview, Context
from trac.util.datefmt import utc, to_timestamp
from trac.attachment import Attachment
from trac.util.translation import _
from datetime import datetime
from cStringIO import StringIO

from utils import parse_rfc2822_date, decode_header
import codecs

import email
import re

from mailinglistplugin.api import MailinglistSystem
from trac.perm import PermissionSystem

class Mailinglist(object):

    def __init__(self, env, id=None,
                 emailaddress=u'',
                 name=u'',
                 description=u'',
                 private=False,
                 date=None,
                 postperm="MEMBERS",
                 replyto="SENDER"):
        self.env = env
        self.id = None
        self.emailaddress = emailaddress.lower()
        self.name = name
        self.description = description
        self.private = private
        if date is None:
            self.date = datetime.now(utc)
        else:
            self.date = date
        self.postperm = postperm
        self.replyto = replyto

        if id is not None:
            row = None
            db = env.get_read_db()
            cursor = db.cursor()
            cursor.execute('SELECT email, name, description, private, date, postperm, replyto '
                           'FROM mailinglist WHERE id = %s', (id,))
            row = cursor.fetchone()
            if row:
                self.id = id
                (self.emailaddress, self.name, self.description,
                 private, date, self.postperm, self.replyto) = row
                self.private = bool(private)
                self.date = datetime.fromtimestamp(date, utc)
            else:
                raise ResourceNotFound(_('Mailinglist %s does not exist.' % id),
                                       _('Invalid Mailinglist Number'))
        self.resource = Resource('mailinglist', self.id)
        
    def __repr__(self):
        return '<%s %r: %s>' % (
            self.__class__.__name__,
            self.emailaddress,
            self.id
        )

    def __nonzero__(self):
        return self.id is not None

    exists = property(__nonzero__)

    def delete(self, db=None):
        """Delete a mailinglist"""
        @self.env.with_transaction(db)
        def do_delete(db):
            cursor = db.cursor()
            cursor.execute('SELECT id FROM mailinglistmessages WHERE list = %s', (self.id,))
            for row in cursor:
                Attachment.delete_all(self.env, 'mailinglistmessages', row[0], db)
            cursor.execute('DELETE FROM mailinglist WHERE id = %s', (self.id,))
            cursor.execute('DELETE FROM mailinglistconversations WHERE list = %s', (self.id,))
            cursor.execute('DELETE FROM mailinglistraw WHERE list = %s', (self.id,))
            cursor.execute('DELETE FROM mailinglistmessages WHERE list = %s', (self.id,))
            cursor.execute('DELETE FROM mailinglistusersubscription WHERE list = %s', (self.id,))
            cursor.execute('DELETE FROM mailinglistgroupsubscription WHERE list = %s', (self.id,))
            cursor.execute('DELETE FROM mailinglistuserdecline WHERE list = %s', (self.id,))
            cursor.execute('DELETE FROM mailinglistusermanager WHERE list = %s', (self.id,))        

        for listener in MailinglistSystem(self.env).mailinglistchange_listeners:
            listener.mailinglist_deleted(self)

    def insert(self, db=None):
        """Add new mailinglist."""
        @self.env.with_transaction(db)
        def do_insert(db):
            cursor = db.cursor()
            cursor.execute('INSERT INTO mailinglist (email, name, description, '
                           'date, private, postperm, replyto) '
                           ' VALUES (%s, %s, %s, %s, %s, %s, %s)',
                           (self.emailaddress.lower(), self.name, self.description, to_timestamp(self.date),
                            self.private and 1 or 0, self.postperm, self.replyto))
            self.id = db.get_last_id(cursor, 'mailinglist')

        for listener in MailinglistSystem(self.env).mailinglistchange_listeners:
            listener.mailinglist_created(self)
        self.resource = Resource('mailinglist', self.id)            
        return self.id

    def save_changes(self, db=None):
        @self.env.with_transaction(db)
        def do_save(db):
            cursor = db.cursor()
            cursor.execute('UPDATE mailinglist SET email=%s, name=%s, description=%s,'
                           'date=%s, private=%s, postperm=%s, replyto=%s WHERE id = %s',
                           (self.emailaddress.lower(), self.name, self.description, to_timestamp(self.date),
                            self.private and 1 or 0, self.postperm, self.replyto, self.id))
            
        for listener in MailinglistSystem(self.env).mailinglistchange_listeners:
            listener.mailinglist_changed(self)
        return True

    def addr(self, bounce=False):
        maildomain = MailinglistSystem(self.env).email_domain
        if bounce:
            return "%s+bounces@%s" % (self.email, self.maildomain)
        else:
            return "%s@%s" % (self.email, self.maildomain)

    def insert_raw_email(self, bytes):
        msg = email.message_from_string(bytes.encode('ascii'))
        
        raw = MailinglistRawMessage(self.env, mailinglist=self, bytes=bytes)
        raw.insert()

        msg_id = msg['message-id']
        references = msg['references']
        in_reply_to = msg['in-reply-to']
        if msg['date']:
            date = parse_rfc2822_date(msg['date'])
        else:
            date = datetime.now(tz.FixedOffsetTimezone(0))
        subject = decode_header(msg['Subject'])

        # Fetch or create a category for the message
        if in_reply_to:
            conv, new = self.get_conv(msg, in_reply_to, subject, date)
        elif references:
            conv, new = self.get_conv(msg, references, subject, date)
        elif 'thread-index' in msg:
            conv, new = self.get_conv_ms(msg, subject, date)
        else:
            conv = MailinglistConversation(self.env, mailinglist=self, date=date, subject=subject)
            conv.insert()
            new = True

        self.env.log.debug("Using conversation %s (new: %s)" % (conv, new))

        # Extract the text/plain body
        body = ''
        for part in msg.walk():
            if part.get_content_type() == 'text/plain':
                missing = object()
                attachment = part.get_param('attachment', missing,
                                            'content-disposition')
                if not attachment is missing:
                    continue
                txt = part.get_payload(decode=True)
                charset = part.get_param('charset', 'ascii')
                # Make sure the charset is supported and fallback to 'ascii'
                # if not
                try:
                    codecs.lookup(charset)
                except LookupError:
                    charset = 'ascii'
                body += txt.decode(charset, 'replace')

        rn, fe = email.Utils.parseaddr(msg['from'])
        from_name = decode_header(rn)
        from_email = decode_header(fe)
        if not from_name: 
            from_name = from_email

        to = decode_header(msg['to'])
        cc = decode_header(msg['cc'])

        m = MailinglistMessage(self.env, conversation=conv, subject=subject,
                               body=body,
                               msg_id=msg_id, date=date,
                               raw=raw, to_header=to, cc_header=cc,
                               from_name=from_name, from_email=from_email)
        m.insert()
        if new:
            conv.first = m
        for part in msg.walk():
            if part.is_multipart():
                continue
            if part.get_content_type == 'text/plain':
                continue
            filename = decode_header(part.get_filename())
            missing = object()
            if not filename or filename is missing:
                    continue
                
            mime_type = part.get_content_type()
            description = decode_header(part.get('content-description',''))
            attachment = Attachment(self.env, 'mailinglistmessage', m.id)
            attachmentbytes = part.get_payload()
            attachment.insert(filename, StringIO(attachmentbytes), len(attachmentbytes))
        
        return m
        

    def get_conv(self, msg, in_reply_to, subject, date):
        """
        Returns the `MailinglistConversation` the msg belongs to. If the message is the
        first message in a conversation or if the conversation is unknown
        a newly created conversation is returned.
        """
        match = re.search('<[^>]+>', in_reply_to)
        if match:
            msg_id = match.group(0)
            self.env.log.debug("Searching for message with msg_id %s", msg_id)
            db = self.env.get_read_db()
            cursor = db.cursor()
            cursor.execute('SELECT conversation '
                           'FROM mailinglistmessages '
                           'WHERE msg_id = %s AND list = %s LIMIT 1', (msg_id, self.id))
            row = cursor.fetchone()
            if row is not None:
                return MailinglistConversation(self.env, row[0]), False

        conv = MailinglistConversation(self.env, mailinglist=self, date=date, subject=subject)
        conv.insert()
        return conv, True

    def get_conv_ms(self, msg, subject, date):
        """
        Returns the `MailinglistConversation` the msg belongs to. If the message is the
        first message in a conversation or if the conversation is unknown
        a newly created conversation is returned.

        Since Microsoft Outlook/exchange seems to send mail replies without
        "In-Reply-To" or "References" headers this version tries to
        locate conversations using the message subject instead.
        """
        if len(subject) > 2 and  subject[2] == ':':
            topic = subject[3:].lstrip()
        else:
            topic = subject
        topic = topic.replace(' ', '')

        self.env.log.debug("Searching for message with topic %s", topic)
        db = self.env.get_read_db()
        cursor = db.cursor()
        cursor.execute('SELECT subject, conversation '
                       'FROM mailinglistmessages '
                       'WHERE list = %s AND date < %s'
                       'ORDER BY DATE LIMIT 1', (self.id, date))
        for row in cursor:
            if subject == row[0].replace(' ',''):
                return MailinglistConversation(self.env, row[1]), False

        conv = MailinglistConversation(self.env, mailinglist=self, date=date, subject=subject)
        conv.insert()
        return conv, True

    @classmethod
    def select(cls, env, db=None):
        if not db:
            db = env.get_read_db()
        cursor = db.cursor()
        cursor.execute("SELECT id FROM mailinglist ORDER BY date")
        for row in cursor:
            yield cls(env, row[0])
            
    @classmethod
    def select_by_address(cls, env, address, db=None):
        userpart = address.lower().split("@",1)[0]
        env.log.debug("Searching for mailinglist for %s", userpart)
        if not db:
            db = env.get_read_db()
        cursor = db.cursor()
        cursor.execute('SELECT id '
                       'FROM mailinglist WHERE email = %s', (userpart,))
        row = cursor.fetchone()
        if row is None:
            raise ResourceNotFound("No mailing list for %s" % address)
        else:
            return Mailinglist(env, row[0])

    def conversations(self):
        cursor = self.env.db.cursor()
        cursor.execute("""SELECT id FROM mailinglistconversations
        WHERE list = %s ORDER BY date""", (self.id,))
        for row in cursor:
            yield MailinglistConversation(self.env, row[0])

    def subscribers(self):
        """
        Return active subscribers of current list and wheather they have
        posting permissions or not.
        """
        res = {}
        all_perms = PermissionSystem(self.env).get_all_permissions()
        # can't use 
        # store.get_users_with_permissions(groupname)
        # because that requires users to be in session table as authenticated users
        for groupname, poster in self.groups():
            for user, permission in all_perms:
                if permission != groupname:
                    continue
                if res.has_key(user):
                    res[user]["poster"] |= poster
                    res[user]["gposter"] |= poster
                    res[user]["groups"].append(groupname)
                else:
                    res[user] = {'groups': [groupname],
                                   'poster':poster,
                                   'gposter':poster,
                                   'individual': False,
                                   'decline': False}
        for username, poster in self.individuals():
            if res.has_key(username):
                res[username]["poster"] |= poster
            else:
                res[username] = {'groups': [],
                                  'poster':poster,
                                  'gposter':False,
                                  'decline': False}
            res[username]['individual'] = username
        for username in self.declines():
            if res.has_key(username):
                res[username]["decline"] = True
        return res

    def subscribe(self, user=None, group=None, poster=False, set_decline=True, db=None):
        if user:
            @self.env.with_transaction(db)
            def do_subscribe(db):
                cursor = db.cursor()
                # #define3 did a count rather than always delete, but
                # that would stop poster being updated?
                cursor.execute("""DELETE FROM mailinglistusersubscription
                WHERE list = %s AND username = %s""", (self.id, user))
                cursor.execute("""INSERT INTO mailinglistusersubscription
                (list, username, poster) values (%s,%s,%s)""", (self.id, user, poster and 1 or 0))
                if set_decline:
                    cursor.execute('DELETE FROM mailinglistuserdecline WHERE list = %s '
                                   'AND username = %s', (self.id, user))
        elif group:
            @self.env.with_transaction(db)
            def do_subscribe(db):
                cursor = db.cursor()
                cursor.execute("""INSERT INTO mailinglistgroupsubscription
                (list, groupname, poster) values (%s,%s,%s)""", (self.id, group, poster and 1 or 0))

    def unsubscribe(self, user=None, group=None, set_decline=True, db=None):
        if user:
            @self.env.with_transaction(db)
            def do_unsubscribe(db):
                cursor = db.cursor()
                # #define3 did a count rather than always delete, but
                # that would stop poster being updated?
                cursor.execute("""DELETE FROM mailinglistusersubscription
                WHERE list = %s AND username = %s""", (self.id, user))
                if set_decline:
                    cursor.execute("""INSERT INTO mailinglistuserdecline
                    (list, username) values (%s,%s)""", (self.id, user))
        elif group:
            @self.env.with_transaction(db)
            def do_unsubscribe(db):
                cursor = db.cursor()
                cursor.execute("""DELETE FROM mailinglistgroupsubscription
                WHERE list = %s AND groupname = %s""", (self.id, group))

    def individuals(self):
        db = self.env.get_read_db()
        cursor = db.cursor()
        cursor.execute('SELECT username, poster FROM mailinglistusersubscription WHERE list = %s', (self.id,))
        for row in cursor:
            yield row[0], bool(row[1])

    def groups(self):
        db = self.env.get_read_db()
        cursor = db.cursor()
        cursor.execute('SELECT groupname, poster FROM mailinglistgroupsubscription WHERE list = %s', (self.id,))
        for row in cursor:
            yield row[0], bool(row[1])

    def declines(self):
        db = self.env.get_read_db()
        cursor = db.cursor()
        cursor.execute('SELECT username FROM mailinglistuserdecline WHERE list = %s', (self.id,))
        for row in cursor:
            yield row[0]

class MailinglistRawMessage(object):

    def __init__(self, env, id=None,
                 mailinglist=None, # Mailinglist instance
                 bytes=''): 
        self.env = env
        self.id = None
        self.mailinglist = mailinglist
        self.bytes = bytes

        if id is not None:
            row = None
            db = env.get_read_db()
            cursor = db.cursor()
            cursor.execute('SELECT list, raw '
                           'FROM mailinglistraw WHERE id = %s', (id,))
            row = cursor.fetchone()
            if row:
                self.id = id
                (mailinglistid, self.bytes) = row 
                self.mailinglist = Mailinglist(env, mailinglistid)
            else:
                raise ResourceNotFound(_('MailinglistRawMessage %s does not exist.' % id),
                                       _('Invalid Mailinglist Raw Message Number'))
        self.resource = Resource('mailinglistrawmessage', self.id,
                                 parent=self.mailinglist.resource)
        
    def __repr__(self):
        return '<%s %r: %s>' % (
            self.__class__.__name__,
            self.title,
            self.id
        )

    def __nonzero__(self):
        return self.id is not None

    exists = property(__nonzero__)

    def delete(self, db=None):
        """Delete a mailinglistrawmessage"""
        @self.env.with_transaction(db)
        def do_delete(db):
            cursor = db.cursor()
            cursor.execute('DELETE FROM mailinglistraw WHERE id = %s', (self.id,))
            
    def insert(self, db=None):
        """Add a new mailinglistrawmessage."""
        @self.env.with_transaction(db)
        def do_insert(db):
            cursor = db.cursor()
            cursor.execute('INSERT INTO mailinglistraw '
                           '(list, raw) '
                           ' VALUES (%s, %s)',
                           (self.mailinglist.id, self.bytes))
            self.id = db.get_last_id(cursor, 'mailinglistraw')
        self.resource = Resource('mailinglistrawmessage', self.id,
                                 parent=self.mailinglist.resource)
        return self.id

    def save_changes(self, db=None):
        @self.env.with_transaction(db)
        def do_save(db):
            cursor = db.cursor()
            cursor.execute('UPDATE mailinglistraw SET list=%s, raw=%s '
                           'WHERE id = %s',
                           (self.mailinglist.id, self.bytes))
        return True


class MailinglistMessage(object):

    def __init__(self, env, id=None,
                 conversation=None, # MailinglistConversation instance
                 subject=u'',
                 body=u'',
                 msg_id=u'',
                 date=None,
                 from_name=u'',
                 from_email=u'',
                 to_header=u'',
                 cc_header=u'',
                 raw=None): # MailinglistRawMessage instance
        
        self.env = env
        self.id = None
        self.conversation = conversation        
        self.subject = subject
        self.body = body
        self.msg_id = msg_id
        if date is None:
            self.date = datetime.now(utc)
        else:
            self.date = date
        self.from_name = from_name
        self.from_email = from_email
        self.to_header = to_header
        self.cc_header = cc_header
        self.raw = raw

        if id is not None:
            row = None
            db = env.get_read_db()
            cursor = db.cursor()
            cursor.execute('SELECT conversation, raw, subject, body, msg_id, '
                           'date, from_name, from_email, to_header, cc_header '
                           'FROM mailinglistmessages WHERE id = %s', (id,))
            row = cursor.fetchone()
            if row:
                self.id = id
                (mailinglistconversationid, mailinglistrawid, self.subject, self.body,
                 self.msg_id, date, self.from_name, self.from_email,
                 self.to_header, self.cc_header) = row 
                self.date = datetime.fromtimestamp(date, utc)
                self.raw = MailinglistRawMessage(env, mailinglistrawid)
                self.conversation = MailinglistConversation(env, mailinglistconversationid)
            else:
                raise ResourceNotFound(_('MailinglistMessage %s does not exist.' % id),
                                       _('Invalid Mailinglist Message Number'))
            
        self.resource = Resource('mailinglistmessage', self.id,
                                 parent=self.conversation.resource)
        
    def __repr__(self):
        return '<%s %r: %s>' % (
            self.__class__.__name__,
            self.subject,
            self.id
        )

    def __nonzero__(self):
        return self.id is not None

    exists = property(__nonzero__)

    def delete(self, db=None):
        """Delete a mailinglistmessage"""
        @self.env.with_transaction(db)
        def do_delete(db):
            cursor = db.cursor()
            Attachment.delete_all(self.env, 'mailinglistmessages', self.id, db)
            cursor.execute("""
            DELETE FROM mailinglistraw WHERE id IN
            (SELECT raw FROM mailinglistmessages WHERE id = %s)""", (self.id,))
            cursor.execute('DELETE FROM mailinglistmessages WHERE id = %s', (self.id,))

        for listener in MailinglistSystem(self.env).messagechange_listeners:
            listener.mailinglistmessage_deleted(self)

    def insert(self, db=None):
        """Save changes or add a new mailinglistmessage."""
        @self.env.with_transaction(db)
        def do_insert(db):
            cursor = db.cursor()
            cursor.execute('INSERT INTO mailinglistmessages '
                           '(conversation, list, raw, subject, body, msg_id, '
                           'date, from_name, from_email, to_header, cc_header) '
                           ' VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                           (self.conversation.id, self.conversation.mailinglist.id, self.raw.id,
                            self.subject, self.body, self.msg_id, to_timestamp(self.date),
                            self.from_name, self.from_email, self.to_header, self.cc_header))
            self.id = db.get_last_id(cursor, 'mailinglistmessages')
            
        for listener in MailinglistSystem(self.env).messagechange_listeners:
            listener.mailinglistmessage_created(self)
        self.resource = Resource('mailinglistmessage', self.id,
                                 parent=self.conversation.resource)
        return self.id

    def save_changes(self, db=None):
        @self.env.with_transaction(db)
        def do_save(db):
            cursor = db.cursor()
            cursor.execute('UPDATE mailinglistmessages SET conversation=%s, list=%s, raw=%s'
                           'subject=%s, body=%s, msg_id=%s, date=%s, '
                           'from_name=%s, from_email=%s, to_header=%s, cc_header=%s'
                           'WHERE id = %s',
                           (self.conversation.id, self.conversation.mailinglist.id, self.raw.id,
                            self.subject, self.body, self.msg_id, to_timestamp(self.date),
                            self.from_name, self.from_email, self.to_header, self.cc_header))

        for listener in MailinglistSystem(self.env).messagechange_listeners:
            listener.mailinglistmessage_changed(self)
            
        return True

class MailinglistConversation(object):

    def __init__(self, env, id=None,
                 mailinglist=None, # Mailinglist instance
                 date=None,
                 subject=u''):
        self.env = env
        self.id = None
        self.mailinglist = mailinglist
        if date is None:
            self.date = datetime.now(utc)
        else:
            self.date = date
        self.subject = subject

        if id is not None:
            row = None
            db = env.get_read_db()
            cursor = db.cursor()
            cursor.execute('SELECT list, date, subject, first '
                           'FROM mailinglistconversations WHERE id = %s', (id,))
            row = cursor.fetchone()
            if row:
                self.id = id
                (mailinglistid, date, self.subject, self._first) = row 
                self.date = datetime.fromtimestamp(date, utc)
                self.mailinglist = Mailinglist(env, mailinglistid)
            else:
                raise ResourceNotFound(_('MailinglistConversation %s does not exist.' % id),
                                       _('Invalid Mailinglist Conversation Number'))
        self.resource = Resource('mailinglistconversation', self.id,
                                 parent=self.mailinglist.resource)
        
    def __repr__(self):
        return '<%s %r: %s>' % (
            self.__class__.__name__,
            self.subject,
            self.id
        )

    def __nonzero__(self):
        return self.id is not None

    exists = property(__nonzero__)

    def delete(self, db=None):
        """Delete a mailinglistconversation"""
        @self.env.with_transaction(db)
        def do_delete(db):
            cursor = db.cursor()
            cursor.execute('SELECT id FROM mailinglistmessages WHERE conversation = %s', (self.id,))
            for row in cursor:
                Attachment.delete_all(self.env, 'mailinglistmessages', row[0], db)
            cursor.execute('DELETE FROM mailinglistconversations WHERE id = %s', (self.id,))
            cursor.execute("""
            DELETE FROM mailinglistraw WHERE id IN
            (SELECT raw FROM mailinglistmessages WHERE conversation = %s)""", (self.id,))
            cursor.execute('DELETE FROM mailinglistmessages WHERE conversation = %s', (self.id,))

        for listener in MailinglistSystem(self.env).conversationchange_listeners:
            listener.mailinglistconversation_deleted(self)

    def insert(self, db=None):
        """Add a new mailinglistconversation."""
        @self.env.with_transaction(db)
        def do_insert(db):
            cursor = db.cursor()
            cursor.execute('INSERT INTO mailinglistconversations (list, date, subject) '
                           ' VALUES (%s, %s, %s)',
                           (self.mailinglist.id, to_timestamp(self.date),
                            self.subject))
            self.id = db.get_last_id(cursor, 'mailinglistconversations')

        for listener in MailinglistSystem(self.env).conversationchange_listeners:
            listener.mailinglistconversation_created(self)
        self.resource = Resource('mailinglistconversation', self.id,
                                 parent=self.mailinglist.resource)
        return self.id

    def save_changes(self, db=None):
        @self.env.with_transaction(db)
        def do_save(db):
            cursor = db.cursor()
            cursor.execute('UPDATE mailinglistconversations SET list=%s, date=%s, subject=%s '
                           'WHERE id = %s',
                           (self.mailinglist.id, to_timestamp(self.date),
                            self.subject, self.id))
        
        for listener in MailinglistSystem(self.env).conversationchange_listeners:
            listener.mailinglistconversation_changed(self)

        return True

    def get_first(self):
        if self._first is None:
            raise ResourceNotFound("First not set")
        return MailinglistMessage(self.env, self._first)

    def set_first(self, message, db=None):
        @self.env.with_transaction(db)
        def do_set(db):
            cursor = db.cursor()
            cursor.execute('UPDATE mailinglistconversations SET first=%s WHERE id = %s',
                           (message.id, self.id))
            self._first = message.id

    first = property(get_first, set_first)

    def messages(self):
        cursor = self.env.db.cursor()
        cursor.execute("""SELECT id FROM mailinglistmessages
        WHERE conversation = %s ORDER BY date""", (self.id,))
        for row in cursor:
            yield MailinglistMessage(self.env, row[0])
