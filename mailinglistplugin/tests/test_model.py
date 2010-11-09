from datetime import datetime, timedelta
import os.path
from StringIO import StringIO
import tempfile
import shutil
import unittest
import time

from trac import core
from trac.attachment import Attachment
from trac.core import TracError, implements
from trac.resource import ResourceNotFound
from trac.test import EnvironmentStub
from trac.util.datefmt import from_utimestamp, to_utimestamp, utc

from mailinglistplugin.api import MailinglistSystem
from mailinglistplugin.model import Mailinglist, Mailinglist

from testdata import rawmsgs, raw_message_with_attachment


from nose.tools import raises



class MailinglistTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        MailinglistSystem(self.env).environment_created()
        
    def tearDown(self):
        self.env.reset_db()

    def test_str_list(self):
        mailinglist = Mailinglist(self.env,
                                  emailaddress="list", name="Sample List", private=True,
                                  postperm="MEMBERS")
        str(mailinglist)

    def test_adding_lists(self):
        for i in range(0,10):
            mailinglist = Mailinglist(self.env,
                                      emailaddress="list%s" % i, name="Sample List", private=True,
                                      postperm="MEMBERS")
            mailinglist.insert()

    def test_removing_lists(self):
        l = []
        for i in range(0,10):
            mailinglist = Mailinglist(self.env,
                                      emailaddress="list%s" % i, name="Sample List", private=True,
                                      postperm="MEMBERS")
            mailinglist.insert()
            l.append(mailinglist.id)
            
        for i in l:
            Mailinglist(self.env, i).delete()
            
    @raises(StandardError) # would be nice to be more specific, but
                           # that depends on which db is used?
    def test_add_duplicate_lists(self):
        Mailinglist(self.env, emailaddress="list", name="Sample List", private=True,
                    postperm="MEMBERS").insert()
        Mailinglist(self.env, emailaddress="list", name="Sample List", private=True,
                    postperm="MEMBERS").insert()

    def test_load_list(self):
        mailinglist = Mailinglist(self.env,
                                  emailaddress="list", name="Sample List", private=True,
                                  postperm="MEMBERS")
        assert mailinglist.id is None
        mailinglist.insert()
        assert mailinglist.id is not None
        found = Mailinglist(self.env, mailinglist.id)
        assert found.id is mailinglist.id
        
    def test_update_private(self):
        mailinglist = Mailinglist(self.env,
                                  emailaddress="list", name="Sample List", private=True,
                                  postperm="MEMBERS")
        assert mailinglist.private == True
        newid = mailinglist.insert()
        mailinglist.private = False
        mailinglist.save_changes()
        assert Mailinglist(self.env, newid).private is False

    def test_add_messages(self):
        mailinglist = Mailinglist(self.env,
                                  emailaddress="LIST1", name="Sample List 1", private=True,
                                  postperm="MEMBERS")
        mailinglist.insert()
        mailinglist = Mailinglist(self.env,
                                  emailaddress="list2", name="Sample List 2", private=True,
                                  postperm="MEMBERS")
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
                                  postperm="MEMBERS")
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
