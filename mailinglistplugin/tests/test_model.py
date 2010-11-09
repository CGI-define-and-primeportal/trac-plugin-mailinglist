from datetime import datetime, timedelta
import os.path
from StringIO import StringIO
import tempfile
import shutil
import unittest
import time

from trac import core
from trac.web.session import DetachedSession
from trac.attachment import Attachment
from trac.core import TracError, implements
from trac.resource import ResourceNotFound
from trac.test import EnvironmentStub
from trac.util.datefmt import from_utimestamp, to_utimestamp, utc

from mailinglistplugin.api import MailinglistSystem
from mailinglistplugin.perm import MailinglistPermissionPolicy
from mailinglistplugin.model import Mailinglist, Mailinglist

from testdata import rawmsgs, raw_message_with_attachment

from trac.perm import PermissionSystem, DefaultPermissionPolicy,\
     PermissionCache, PermissionError, DefaultPermissionStore

from nose.tools import raises

# need this for MailinglistSystem(self.env).environment_created()
from trac.db.sqlite_backend import SQLiteConnector


class MailinglistTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(enable=[MailinglistPermissionPolicy,
                                           DefaultPermissionPolicy,
                                           MailinglistSystem,
                                           DefaultPermissionStore,
                                           SQLiteConnector])
        self.env.config.set('trac', 'permission_policies', 'MailinglistPermissionPolicy, DefaultPermissionPolicy')

        self.mailinglist_system = MailinglistSystem(self.env)
        self.mailinglist_system.environment_created()

        self.perm_system = PermissionSystem(self.env)
        
    def tearDown(self):
        self.env.reset_db()

    def test_str_list(self):
        mailinglist = Mailinglist(self.env,
                                  emailaddress="list", name="Sample List", private=True,
                                  postperm="OPEN")
        str(mailinglist)

    def test_adding_lists(self):
        for i in range(0,10):
            mailinglist = Mailinglist(self.env,
                                      emailaddress="list%s" % i, name="Sample List", private=True,
                                      postperm="OPEN")
            mailinglist.insert()

    def test_removing_lists(self):
        l = []
        for i in range(0,10):
            mailinglist = Mailinglist(self.env,
                                      emailaddress="list%s" % i, name="Sample List", private=True,
                                      postperm="OPEN")
            mailinglist.insert()
            l.append(mailinglist.id)
            
        for i in l:
            Mailinglist(self.env, i).delete()
            
    @raises(StandardError) # would be nice to be more specific, but
                           # that depends on which db is used?
    def test_add_duplicate_lists(self):
        Mailinglist(self.env, emailaddress="list", name="Sample List", private=True,
                    postperm="OPEN").insert()
        Mailinglist(self.env, emailaddress="list", name="Sample List", private=True,
                    postperm="OPEN").insert()

    def test_load_list(self):
        mailinglist = Mailinglist(self.env,
                                  emailaddress="list", name="Sample List", private=True,
                                  postperm="OPEN")
        assert mailinglist.id is None
        mailinglist.insert()
        assert mailinglist.id is not None
        found = Mailinglist(self.env, mailinglist.id)
        assert found.id is mailinglist.id
        
    def test_update_private(self):
        mailinglist = Mailinglist(self.env,
                                  emailaddress="list", name="Sample List", private=True,
                                  postperm="OPEN")
        assert mailinglist.private == True
        newid = mailinglist.insert()
        mailinglist.private = False
        mailinglist.save_changes()
        assert Mailinglist(self.env, newid).private is False

    def test_add_messages(self):
        mailinglist = Mailinglist(self.env,
                                  emailaddress="LIST1", name="Sample List 1", private=True,
                                  postperm="OPEN")
        mailinglist.insert()
        mailinglist = Mailinglist(self.env,
                                  emailaddress="list2", name="Sample List 2", private=True,
                                  postperm="OPEN")
        mailinglist.insert()

        for rawmsg in rawmsgs:
            for listname in ("list1", "list2"):
                bytes = rawmsg % dict(sender="Jack Sparrow",
                                      email="jack@example.com",
                                      list=listname,
                                      domain="example.com",
                                      subject="Boats",
                                      asctime=time.asctime(),
                                      id="asdfasdf",
                                      body="Need boats.")

                mailinglist = Mailinglist.select_by_address(self.env,
                                                            "%s@example.com" % listname)
                message = mailinglist.insert_raw_email(bytes)
                
        assert len(list(Mailinglist.select(self.env))) == 2
        
        for mailinglist in Mailinglist.select(self.env):
            for conversation in mailinglist.conversations():
                assert conversation.get_first() is not None
                for message in conversation.messages():
                    assert message
                    for attachment in Attachment.select(self.env, 'mailinglistmessage', message.id):
                        assert attachment

            mailinglist.delete()
            
        assert len(list(Mailinglist.select(self.env))) == 0
        

    def test_add_message_with_attachment(self):
        mailinglist = Mailinglist(self.env,
                                  emailaddress="LIST1", name="Sample List 1", private=True,
                                  postperm="OPEN")
        mailinglist.insert()
        
        mailinglist.insert_raw_email(raw_message_with_attachment % dict(sender="Jack Sparrow",
                                                                        email="jack@example.com",
                                                                        list="list1",
                                                                        domain="example.com",
                                                                        subject="Boats",
                                                                        asctime=time.asctime(),
                                                                        id="asdfasdf",
                                                                        body="Need images of boats."))
        
        message = mailinglist.conversations().next().messages().next()
        assert Attachment.select(self.env, message.resource.realm, message.resource.id).next().filename

    def test_add_list_member(self):
        mailinglist = Mailinglist(self.env,
                                  emailaddress="LIST1", private=True, postperm="MEMBERS")
        mailinglist.insert()
        mailinglist.subscribe(user="sparrowj", poster=True)
        assert "sparrowj" in mailinglist.subscribers()

    @raises(PermissionError)
    def test_post_to_private_list_denied_members(self):
        """Not a member of this list."""
        mailinglist = Mailinglist(self.env,
                                  emailaddress="LIST1", private=True, postperm="MEMBERS")
        mailinglist.insert()
        mailinglist.subscribe(user="smithj", poster=True)
        PermissionCache(self.env, 'sparrowj',
                        mailinglist.resource).assert_permission('MAILINGLIST_POST')

    @raises(PermissionError)
    def test_post_to_private_list_denied_restricted(self):
        """Non-posting member of this list."""        
        mailinglist = Mailinglist(self.env,
                                  emailaddress="LIST1", private=True, postperm="RESTRICTED")
        mailinglist.insert()
        mailinglist.subscribe(user="sparrowj", poster=False)
        PermissionCache(self.env, 'sparrowj',
                        mailinglist.resource).assert_permission('MAILINGLIST_POST')

    @raises(PermissionError)
    def test_post_to_private_list_denied_restricted_nonmember(self):
        """Non-posting member of this list."""        
        mailinglist = Mailinglist(self.env,
                                  emailaddress="LIST1", private=True, postperm="RESTRICTED")
        mailinglist.insert()
        mailinglist.subscribe(user="sparrowj", poster=False)
        PermissionCache(self.env, 'smithj',
                        mailinglist.resource).assert_permission('MAILINGLIST_POST')

    def test_post_to_private_list_accepted_members(self):
        mailinglist = Mailinglist(self.env,
                                  emailaddress="LIST1", private=True, postperm="MEMBERS")
        mailinglist.insert()
        mailinglist.subscribe(user="sparrowj", poster=True)
        PermissionCache(self.env, 'sparrowj',
                        mailinglist.resource).assert_permission('MAILINGLIST_POST')

    def test_post_to_private_list_accepted_members_group(self):
        mailinglist = Mailinglist(self.env,
                                  emailaddress="LIST1", private=True, postperm="MEMBERS")
        mailinglist.insert()
        PermissionSystem(self.env).grant_permission('sparrowj', 'group1')
        PermissionSystem(self.env).grant_permission('smithj', 'group1')        
        mailinglist.subscribe(group="group1", poster=True)
        PermissionCache(self.env, 'sparrowj',
                        mailinglist.resource).assert_permission('MAILINGLIST_POST')

    def test_post_to_private_list_accepted_restricted(self):
        mailinglist = Mailinglist(self.env,
                                  emailaddress="LIST1", private=True, postperm="RESTRICTED")
        mailinglist.insert()
        mailinglist.subscribe(user="smithj", poster=False)        
        mailinglist.subscribe(user="sparrowj", poster=True)
        PermissionCache(self.env, 'sparrowj',
                        mailinglist.resource).assert_permission('MAILINGLIST_POST')

    def test_subscribers(self):
        mailinglist = Mailinglist(self.env,
                                  emailaddress="LIST1", private=True, postperm="MEMBERS")
        mailinglist.insert()
        PermissionSystem(self.env).grant_permission('sparrowj', 'group1')
        PermissionSystem(self.env).grant_permission('smithj', 'group1')
        PermissionSystem(self.env).grant_permission('pipern', 'group2')
        mailinglist.subscribe(group="group1", poster=True)
        mailinglist.subscribe(group="group2", poster=True)
        mailinglist.unsubscribe(user="smithj")

        assert mailinglist.subscribers()["smithj"]['decline'] == True
        assert "sparrowj" in mailinglist.subscribers()
        assert "pipern" in mailinglist.subscribers()

        mailinglist.unsubscribe(group="group1")
        assert "sparrowj" not in mailinglist.subscribers()        

    def test_read_private_list_accepted(self):
        mailinglist = Mailinglist(self.env,
                                  emailaddress="LIST1", private=True, postperm="RESTRICTED")
        mailinglist.insert()
        mailinglist.subscribe(user="smithj", poster=False)        
        mailinglist.subscribe(user="sparrowj", poster=True)
        PermissionCache(self.env, 'sparrowj',
                        mailinglist.resource).assert_permission('MAILINGLIST_VIEW')

    def test_read_nonprivate_list_accepted(self):
        PermissionSystem(self.env).grant_permission('members', 'MAILINGLIST_VIEW')
        PermissionSystem(self.env).grant_permission('randomuser', 'members')
        mailinglist = Mailinglist(self.env,
                                  emailaddress="LIST1", private=False, postperm="RESTRICTED")
        mailinglist.insert()
        mailinglist.subscribe(user="smithj", poster=False)        
        mailinglist.subscribe(user="sparrowj", poster=True)
        PermissionCache(self.env, 'randomuser',
                        mailinglist.resource).assert_permission('MAILINGLIST_VIEW')

    @raises(PermissionError)
    def test_read_nonprivate_list_denied(self):
        # not a private list, but in general the user isn't allowed to
        # view mailing lists (e.g., not a member of this project at all.)
        mailinglist = Mailinglist(self.env,
                                  emailaddress="LIST1", private=False, postperm="RESTRICTED")
        mailinglist.insert()
        mailinglist.subscribe(user="smithj", poster=False)        
        mailinglist.subscribe(user="sparrowj", poster=True)
        PermissionCache(self.env, 'randomuser',
                        mailinglist.resource).assert_permission('MAILINGLIST_VIEW')

    @raises(PermissionError)
    def test_read_private_list_denied(self):
        mailinglist = Mailinglist(self.env,
                                  emailaddress="LIST1", private=True, postperm="RESTRICTED")
        mailinglist.insert()
        mailinglist.subscribe(user="smithj", poster=False)        
        mailinglist.subscribe(user="sparrowj", poster=True)
        PermissionCache(self.env, 'randomuser',
                        mailinglist.resource).assert_permission('MAILINGLIST_VIEW')
