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

from mailinglistplugin.mailinglist import MailinglistSystem
from mailinglistplugin.model import Mailinglist, Mailinglist

from nose.tools import raises

rawmsgs = ["""\
From: %(sender)s <%(email)s>
To: List <%(list)s@%(domain)s>
Subject: %(subject)s
Date: %(asctime)s
Message-Id: <%(id)s@example.com>

%(body)s
"""]

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
            mailinglist.save()

    @raises(StandardError) # would be nice to be more specific, but
                           # that depends on which db is used?
    def test_add_duplicate_lists(self):
        Mailinglist(self.env, emailaddress="list", name="Sample List", private=True,
                    postperm="MEMBERS").save()
        Mailinglist(self.env, emailaddress="list", name="Sample List", private=True,
                    postperm="MEMBERS").save()

    def test_load_list(self):
        mailinglist = Mailinglist(self.env,
                                  emailaddress="list", name="Sample List", private=True,
                                  postperm="MEMBERS")
        assert mailinglist.id is None
        mailinglist.save()
        assert mailinglist.id is not None
        found = Mailinglist(self.env, mailinglist.id)
        assert found.id is mailinglist.id
        
    def test_update_private(self):
        mailinglist = Mailinglist(self.env,
                                  emailaddress="list", name="Sample List", private=True,
                                  postperm="MEMBERS")
        assert mailinglist.private == True
        mailinglist.private = False
        mailinglist.save()
        assert Mailinglist(self.env, mailinglist.id).private is False

    def test_add_messages(self):
        mailinglist = Mailinglist(self.env,
                                  emailaddress="LIST1", name="Sample List 1", private=True,
                                  postperm="MEMBERS")
        mailinglist.save()
        mailinglist = Mailinglist(self.env,
                                  emailaddress="list2", name="Sample List 2", private=True,
                                  postperm="MEMBERS")
        mailinglist.save()

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

                mailinglist = MailinglistSystem(self.env).find_mailinglist_for_address(
                    "%s@example.com" % listname)
                message = mailinglist.insert_raw_email(bytes)
                
