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
from trac.resource import ResourceNotFound
import email
from utils import decode_header

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
    implements(IEnvironmentSetupParticipant, IPermissionRequestor)

    mailinglistchange_listeners  = ExtensionPoint(IMailinglistChangeListener)
    conversationchange_listeners = ExtensionPoint(IMailinglistConversationChangeListener)
    messagechange_listeners      = ExtensionPoint(IMailinglistMessageChangeListener)


    email_domain = Option('discussion', 'email_domain', '',
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
        self.log.debug("Upgrading schema for metadata plugin")
        db_backend, _ = DatabaseManager(self.env)._get_connector()
        cursor = db.cursor()
        for table in self._schema:
            for stmt in db_backend.to_sql(table):
                self.log.debug(stmt)
                cursor.execute(stmt)
    
