from optparse import OptionParser
import os
import mailbox
from trac.env import open_environment
from trac.resource import ResourceNotFound
from mailinglistplugin.model import Mailinglist

class mbox_to_mailinglist_importer:
    """Import Maildir directory into a new Trac mailinglist.

    """
    product="mbox"
    
    def import_project(self, sourcepath, destinationpath, name=None, **kwargs):

        if name is None:
            raise KeyError("This importer requires a Trac project to already exist. Use --name to specify it's dir name.")
        
        env_path = os.path.join(destinationpath, name)
        mailinglist_name = os.path.basename(sourcepath.rstrip("/"))
        env = open_environment(env_path)

        try:
            mailinglist = Mailinglist.select_by_address(env, mailinglist_name, localpart=True)
        except ResourceNotFound:
            mailinglist = Mailinglist(env, emailaddress=mailinglist_name, name="Imported list",
                                      private=True, postperm="MEMBERS", replyto="LIST")
            mailinglist.insert()

        mbox = mailbox.Maildir(sourcepath)

        for mail in mbox:
            mail.fp.seek(0)
            mailinglist.insert_raw_email(mail.fp.read())
        
        
