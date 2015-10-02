# -*- coding: utf-8 -*-
#
# Copyright (C) 2010 Logica
# All rights reserved.
#

from trac.web.chrome import ITemplateProvider, add_script, add_stylesheet, Chrome, add_notice
from trac.web.api import ITemplateStreamFilter, IRequestFilter
from trac.core import Component, implements, TracError, Interface, ExtensionPoint
from trac.config import ExtensionOption, Option, ListOption
from trac.perm import IPermissionRequestor, IPermissionPolicy
from trac.admin.api import IAdminPanelProvider
from trac.cache import cached
from trac.db import Table, Column, Index
from trac.db import DatabaseManager
from trac.env import IEnvironmentSetupParticipant
from trac.util.datefmt import from_utimestamp, to_utimestamp, utc, utcmax, format_datetime
from trac.config import BoolOption, Option
from trac.resource import IResourceManager, ResourceNotFound
import email
from utils import decode_header
from announcer.api import AnnouncementSystem, IAnnouncementProducer, \
     AnnouncementEvent, IAnnouncementSubscriber, IAnnouncementFormatter

class IMailinglistChangeListener(Interface):
    """Extension point interface for components that require notification
    when mailinglists are created, modified, or deleted."""

    def mailinglist_created(mailinglist):
        """Called when a mailinglist is created."""

    def mailinglist_changed(mailinglist):
        """Called when a mailinglist is modified."""

    def mailinglist_deleted(mailinglist):
        """Called when a mailinglist is deleted."""

class IMailinglistConversationChangeListener(Interface):
    """Extension point interface for components that require notification
    when mailinglistconversations are created, modified, or deleted."""

    def mailinglistconversation_created(mailinglistconversation):
        """Called when a mailinglistconversation is created."""

    def mailinglistconversation_changed(mailinglistconversation):
        """Called when a mailinglistconversation is modified."""

    def mailinglistconversation_deleted(mailinglistconversation):
        """Called when a mailinglistconversation is deleted."""

class IMailinglistMessageChangeListener(Interface):
    """Extension point interface for components that require notification
    when mailinglistmessages are created, modified, or deleted."""

    def mailinglistmessage_created(mailinglistmessage):
        """Called when a mailinglistmessage is created."""

    def mailinglistmessage_changed(mailinglistmessage):
        """Called when a mailinglistmessage is modified."""

    def mailinglistmessage_deleted(mailinglistmessage):
        """Called when a mailinglistmessage is deleted."""

class MailinglistSystem(Component):
    implements(IEnvironmentSetupParticipant, IPermissionRequestor,
               IMailinglistMessageChangeListener,
               IAnnouncementProducer, IAnnouncementFormatter, IAnnouncementSubscriber,
               IResourceManager)

    mailinglistchange_listeners  = ExtensionPoint(IMailinglistChangeListener)
    conversationchange_listeners = ExtensionPoint(IMailinglistConversationChangeListener)
    messagechange_listeners      = ExtensionPoint(IMailinglistMessageChangeListener)


    email_domain = Option('mailinglist', 'email_domain', '',
      'Domain to show in the inbound email addresses.')

    # IPermissionRequestor methods
    def get_permission_actions(self):
        """ Permissions supported by the plugin. """
        return ['MAILINGLIST_VIEW',
                'MAILINGLIST_CREATE',
                'MAILINGLIST_DELETE',
                'MAILINGLIST_POST',
                ('MAILINGLIST_ADMIN', ['MAILINGLIST_VIEW',
                                       'MAILINGLIST_POST',                                       
                                       'MAILINGLIST_CREATE',
                                       'MAILINGLIST_DELETE'])]

    # IEnvironmentSetupParticipant
    _schema = [
        Table('mailinglist', key='id')[
            Column('id', auto_increment=True),
            Column('email'),
            Column('name'),
            Column('description'),
            Column('date', type='int64'),
            Column('private', type='int'),
            Column('postperm'), # OPEN, MEMBERS, RESTRICTED
            Column('replyto'), # SENDER, LIST
            Index(['email'], unique=True),
            ],
        Table('mailinglistconversations', key=('id'))[
            Column('id', auto_increment=True),
            Column('list', type='int'),
            Column('date', type='int64'),
            Column('subject'),
            Column('first', type='int'),
            ],
        Table('mailinglistraw', key=('id'))[
            Column('id', auto_increment=True),
            Column('list', type='int'),
            Column('raw'),
            ],
        Table('mailinglistmessages', key=('id'))[
            Column('id', auto_increment=True),
            Column('list', type='int'),
            Column('conversation', type='int'),
            Column('raw', type='int'),
            Column('subject'),
            Column('body'),
            Column('msg_id'),
            Column('date', type='int64'),
            Column('from_name'),
            Column('from_email'),
            Column('to_header'),
            Column('cc_header'),
            Index(['list']),
            Index(['conversation']),            
            ],
        Table('mailinglistusersubscription', key=('id'))[
            Column('id', auto_increment=True),
            Column('list', type='int'),
            Column('username'),
            Column('poster', type='int'),
            Index(['list','username']),
            ],
        Table('mailinglistgroupsubscription', key=('id'))[
            Column('id', auto_increment=True),
            Column('list', type='int'),
            Column('groupname'),
            Column('poster', type='int'),
            Index(['list','groupname']),
            ],
        Table('mailinglistuserdecline', key=('id'))[
            Column('id', auto_increment=True),
            Column('list', type='int'),
            Column('username'),
            Index(['list','username']),
            ],
        ]

    def environment_created(self):
        self.upgrade_environment(self.env.get_db_cnx())

    def environment_needs_upgrade(self, db):
        try:
            @self.env.with_transaction()
            def check(db):
                sql = "select count(*) from mailinglist"
                cursor = db.cursor()
                cursor.execute(sql)
                cursor.fetchone()
        except Exception, e:
            self.log.debug("Upgrade of schema needed for mailinglist plugin", exc_info=True)
            return True
        else:
            return False

    def upgrade_environment(self, db):
        self.log.debug("Upgrading schema for mailinglist plugin")
        db_backend, _ = DatabaseManager(self.env)._get_connector()
        cursor = db.cursor()
        for table in self._schema:
            for stmt in db_backend.to_sql(table):
                self.log.debug(stmt)
                cursor.execute(stmt)

    # IResourceManager

    def get_resource_realms(self):
        yield "mailinglist"

    def get_resource_url(self, resource, href, **kwargs):
        return href.mailinglist(resource.id, **kwargs)
        
    def get_resource_description(self, resource, format=None, context=None,
                                 **kwargs):
        instance = self.get_instance_for_resource(resource)
        if format in ("compact", "default"):
            if hasattr(instance, "name"):
                return instance.name
            elif hasattr(instance, "subject"):
                return instance.subject
        elif format == "summary":
            if hasattr(instance, "description"):
                return instance.description
            elif hasattr(instance, "subject"):
                return instance.subject
            
    def resource_exists(self, resource):
        try:
            return bool(self.get_instance_for_resource(resource))
        except ResourceNotFound:
            return False

    def get_instance_for_resource(self, resource):
        if resource.realm != "mailinglist":
            return None
        parts = resource.id.split("/")
        if len(parts) == 0:
            return None
        elif len(parts) == 1:
            from mailinglistplugin.model import Mailinglist
            return Mailinglist.select_by_address(self.env, parts[0], localpart=True)
        elif len(parts) == 2:
            from mailinglistplugin.model import MailinglistConversation
            return MailinglistConversation(self.env, int(parts[1]))
        elif len(parts) == 3:
            if parts[2] == "raw":
                from mailinglistplugin.model import MailinglistRawMessage
                return MailinglistRawMessage(self.env, int(parts[2]))
            else:
                from mailinglistplugin.model import MailinglistMessage
                return MailinglistMessage(self.env, int(parts[2]))
    
    # IMailinglistMessageChangeListener

    def mailinglistmessage_created(self, message):
        """Called when a mailinglistmessage is created."""
        announcer = AnnouncementSystem(self.env)
        announcer.send(MailinglistMessageEvent('mailinglist', 'created', message))

    def mailinglistmessage_changed(self, message):
        """Called when a mailinglistmessage is modified."""

    def mailinglistmessage_deleted(self, message):
        """Called when a mailinglistmessage is deleted."""

    # IAnnouncementProducer methods
    
    def realms(self):
        yield 'mailinglist'

    # IAnnouncementFormatter

    def styles(self, transport, realm):
        if realm == "discussion":
            yield "text/html"
        elif realm == "mailinglist":
            yield "verbatim"
        
    def alternative_style_for(self, transport, realm, style):
        return None
        
    def format(self, transport, realm, style, event):
        if realm == "mailinglist" and style == "verbatim":
            mail = email.message_from_string(event.target.raw.bytes)
            self._set_header(mail, 'X-BeenThere', event.target.conversation.mailinglist.addr(), append=True)
            self._set_header(mail, 'Precedence', 'list')
            self._set_header(mail, 'Errors-To', event.target.conversation.mailinglist.addr(bounce=True))            
            self._set_header(mail, 'Return-Path', event.target.conversation.mailinglist.addr(bounce=True))
            self._set_header(mail, 'List-Id', event.target.conversation.mailinglist.addr())
            if event.target.conversation.mailinglist.replyto == 'LIST':
                self._set_header(mail, 'Reply-To', event.target.conversation.mailinglist.addr())
            elif event.target.from_email:
                self._set_header(mail, 'Reply-To', event.target.from_email)
            return mail
                
    def _set_header(self, mail, header, value, charset=None, append=False):
        if append and mail[header]:
            h = email.Header.decode_header(mail[header])
            h.append((value, charset))
            mail[header] = email.Header.make_header(h)
            return
        else:
            del mail[header]
        mail[header] = email.Header.Header(value, charset=charset)

    # IAnnouncementSubscriber methods

    def subscriptions(self, event):
        if event.realm is not 'mailinglist':
            return

        for subscriber, details in event.target.conversation.mailinglist.subscribers().items():
            if details['decline']:
                self.log.debug("Subscriber declined for %s is %s (%s)", event.target, subscriber, details)                
                continue
            self.log.debug("Subscriber for %s is %s (%s)", event.target, subscriber, details)
            yield ("email", subscriber, True, None)
  
class MailinglistMessageEvent(AnnouncementEvent):
    def __init__(self, realm, category, target):
        AnnouncementEvent.__init__(self, realm, category, target)
