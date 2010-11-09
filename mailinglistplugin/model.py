# -*- coding: utf-8 -*-

from trac.core import *
from trac.resource import Resource, ResourceNotFound
from trac.mimeview.api import Mimeview, Context
from trac.util.datefmt import utc, to_timestamp
from trac.util.translation import _
from datetime import datetime

from utils import parse_rfc2822_date, decode_header


import email

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
            db = env.get_db_cnx()
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
        if db:
            handle_ta = False
        else:
            handle_ta = True
            db = self.env.get_db_cnx()
        cursor = db.cursor()

        if self.id is None:
            raise ValueError('cannot delete not existing mailinglist')

        # TODO: Delete attachments too?
        cursor.execute('DELETE FROM mailinglist WHERE id = %s', (self.id,))
        cursor.execute('DELETE FROM mailinglistconversations WHERE list = %s', (self.id,))
        cursor.execute('DELETE FROM mailinglistraw WHERE list = %s', (self.id,))
        cursor.execute('DELETE FROM mailinglistmessages WHERE list = %s', (self.id,))
        cursor.execute('DELETE FROM mailinglistusersubscription WHERE list = %s', (self.id,))
        cursor.execute('DELETE FROM mailinglistgroupsubscription WHERE list = %s', (self.id,))
        cursor.execute('DELETE FROM mailinglistuserdecline WHERE list = %s', (self.id,))
        cursor.execute('DELETE FROM mailinglistusermanager WHERE list = %s', (self.id,))        

        if handle_ta:
            db.commit()

    def save(self, db=None):
        """Save changes or add a new mailinglist."""
        if db:
            handle_ta = False
        else:
            handle_ta = True
            db = self.env.get_db_cnx()
        cursor = db.cursor()

        if self.id is None:
            cursor.execute('INSERT INTO mailinglist (email, name, description, '
                           'date, private, postperm, replyto) '
                           ' VALUES (%s, %s, %s, %s, %s, %s, %s)',
                           (self.emailaddress.lower(), self.name, self.description, to_timestamp(self.date),
                            self.private and 1 or 0, self.postperm, self.replyto))
            self.id = db.get_last_id(cursor, 'mailinglist')
        else:
            cursor.execute('UPDATE mailinglist SET email=%s, name=%s, description=%s,'
                           'date=%s, private=%s, postperm=%s, replyto=%s WHERE id = %s',
                           (self.emailaddress.lower(), self.name, self.description, to_timestamp(self.date),
                            self.private and 1 or 0, self.postperm, self.replyto, self.id))

        if handle_ta:
            db.commit()

    def addr(self, bounce=False):
        maildomain = MailinglistSystem(self.env).email_domain
        if bounce:
            return "%s+bounces@%s" % (self.email, self.maildomain)
        else:
            return "%s@%s" % (self.email, self.maildomain)

    def insert_raw_email(self, bytes):
        msg = email.message_from_string(bytes.encode('ascii'))
        
        raw = MailinglistRawMessage(self.env, mailinglist=self, bytes=bytes)
        raw.save()

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
            conv, new = self.new_conv(subject, date)        
        
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
            db = env.get_db_cnx()
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
        if db:
            handle_ta = False
        else:
            handle_ta = True
            db = self.env.get_db_cnx()
        cursor = db.cursor()

        if self.id is None:
            raise ValueError('cannot delete not existing mailinglistrawmessage')

        cursor.execute('DELETE FROM mailinglistraw WHERE id = %s', (self.id,))

        if handle_ta:
            db.commit()

    def save(self, db=None):
        """Save changes or add a new mailinglistrawmessage."""
        if db:
            handle_ta = False
        else:
            handle_ta = True
            db = self.env.get_db_cnx()
        cursor = db.cursor()

        if self.id is None:
            cursor.execute('INSERT INTO mailinglistraw '
                           '(list, raw) '
                           ' VALUES (%s, %s)',
                           (self.mailinglist.id, self.bytes))
            self.id = db.get_last_id(cursor, 'mailinglistraw')
        else:
            cursor.execute('UPDATE mailinglistraw SET list=%s, raw=%s '
                           'WHERE id = %s',
                           (self.mailinglist.id, self.bytes))

        if handle_ta:
            db.commit()


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
            db = env.get_db_cnx()
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
            self.title,
            self.id
        )

    def __nonzero__(self):
        return self.id is not None

    exists = property(__nonzero__)

    def delete(self, db=None):
        """Delete a mailinglistmessage"""
        if db:
            handle_ta = False
        else:
            handle_ta = True
            db = self.env.get_db_cnx()
        cursor = db.cursor()

        if self.id is None:
            raise ValueError('cannot delete not existing mailinglistmessage')

        # TODO: Delete attachments too?
        cursor.execute("""
        DELETE FROM mailinglistraw WHERE id IN
        (SELECT raw FROM mailinglistmessages WHERE id = %s)""", (self.id,))
        cursor.execute('DELETE FROM mailinglistmessages WHERE id = %s', (self.id,))

        if handle_ta:
            db.commit()

    def save(self, db=None):
        """Save changes or add a new mailinglistmessage."""
        if db:
            handle_ta = False
        else:
            handle_ta = True
            db = self.env.get_db_cnx()
        cursor = db.cursor()

        if self.id is None:
            cursor.execute('INSERT INTO mailinglistmessage '
                           '(conversation, mailinglist, raw, subject, body, msg_id, '
                           'date, from_name, from_email, to_header, cc_header) '
                           ' VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                           (self.conversation.id, self.conversation.mailinglist.id, self.raw.id,
                            self.subject, self.body, self.msg_id, to_timestamp(self.date),
                            self.from_name, self.from_email, self.to_header, self.cc_header))
            self.id = db.get_last_id(cursor, 'mailinglistmessage')
        else:
            cursor.execute('UPDATE mailinglistmessage SET conversation=%s, mailinglist=%s, raw=%s'
                           'subject=%s, body=%s, msg_id=%s, date=%s, '
                           'from_name=%s, from_email=%s, to_header=%s, cc_header=%s'
                           'WHERE id = %s',
                           (self.conversation.id, self.conversation.mailinglist.id, self.raw.id,
                            self.subject, self.body, self.msg_id, to_timestamp(self.date),
                            self.from_name, self.from_email, self.to_header, self.cc_header))

        if handle_ta:
            db.commit()

class MailinglistConversation(object):

    def __init__(self, env, id=None,
                 mailinglist=None, # Mailinglist instance
                 date=None,
                 subject=u'',
                 first=None): # MailinglistMessage instance
        self.env = env
        self.id = None
        self.mailinglist = mailinglist
        if date is None:
            self.date = datetime.now(utc)
        else:
            self.date = date
        self.subject = subject
        self.first = first

        if id is not None:
            row = None
            db = env.get_db_cnx()
            cursor = db.cursor()
            cursor.execute('SELECT list, date, subject, first '
                           'FROM mailinglistconversation WHERE id = %s', (id,))
            row = cursor.fetchone()
            if row:
                self.id = id
                (mailinglistid, date, self.subject, mailinglistmessageid) = row 
                self.date = datetime.fromtimestamp(date, utc)
                self.mailinglist = Mailinglist(env, mailinglistid)
                try:
                    self.first = MailinglistMessage(env, mailinglistmessageid)
                except ResourceNotFound, e:
                    self.first = None
            else:
                raise ResourceNotFound(_('MailinglistConversation %s does not exist.' % id),
                                       _('Invalid Mailinglist Conversation Number'))
        self.resource = Resource('mailinglistconversation', self.id,
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
        """Delete a mailinglistconversation"""
        if db:
            handle_ta = False
        else:
            handle_ta = True
            db = self.env.get_db_cnx()
        cursor = db.cursor()

        if self.id is None:
            raise ValueError('cannot delete not existing mailinglistconversation')

        # TODO: Delete attachments too?
        cursor.execute('DELETE FROM mailinglistconversations WHERE id = %s', (self.id,))
        cursor.execute("""
        DELETE FROM mailinglistraw WHERE id IN
        (SELECT raw FROM mailinglistmessages WHERE conversation = %s)""", (self.id,))
        cursor.execute('DELETE FROM mailinglistmessages WHERE conversation = %s', (self.id,))

        if handle_ta:
            db.commit()

    def save(self, db=None):
        """Save changes or add a new mailinglistconversation."""
        if db:
            handle_ta = False
        else:
            handle_ta = True
            db = self.env.get_db_cnx()
        cursor = db.cursor()

        if self.id is None:
            cursor.execute('INSERT INTO mailinglistconversations (list, date, subject, first) '
                           ' VALUES (%s, %s, %s, %s)',
                           (self.mailinglist.id, to_timestamp(self.date),
                            self.subject, self.first and self.first.id or None))
            self.id = db.get_last_id(cursor, 'mailinglistconversations')
        else:
            cursor.execute('UPDATE mailinglistconversations SET list=%s, date=%s, subject=%s,'
                           'first=%s WHERE id = %s',
                           (self.mailinglist.id, to_timestamp(self.date),
                            self.subject, self.first and self.first.id or None))

        if handle_ta:
            db.commit()
