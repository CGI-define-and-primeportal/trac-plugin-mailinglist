import os
import mailbox
import time
import tempfile
import gzip

from threading import Thread
from dateutil.parser import parse as parse_date
from datetime import datetime
from ConfigParser import ConfigParser

try:
    from xml.etree import ElementTree as et
    import json
    from hashlib import md5
except ImportError:
    from elementtree import ElementTree as et
    import simplejson as json
    from md5 import new as md5

from trac.util.datefmt import utc
from trac.env import open_environment
from trac.resource import ResourceNotFound
from trac.util.datefmt import utc, parse_date
from trac.config import _TRUE_VALUES
from mailinglistplugin.model import Mailinglist


def to_bool(s):
    try:
        return s.lower() in _TRUE_VALUES
    except:
        return bool(s)
        

class maildir_to_mailinglist_importer:
    """Import Maildir directory into a new Trac mailinglist.
    See http://docs.python.org/library/mailbox.html#mailbox.Maildir
    """
    product="Maildir"
    
    def import_project(self, sourcepath, destinationpath, name=None, **kwargs):

        if name is None:
            raise KeyError("This importer requires a Trac project to already exist. Use --name to specify it's dir name.")
        
        env_path = os.path.join(destinationpath, name)
        mailinglist_name = os.path.basename(sourcepath.rstrip("/"))
        env = open_environment(env_path)

        #mailinglist = Mailinglist.select_by_address(env, mailinglist_name, localpart=True)
        #mailinglist.delete()

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
        
class mbox_to_mailinglist_importer(object):
    """Import mbox file into a new Trac mailinglist.
    Imports either a single mbox file (optionally gzipped) or all mbox files (optionally gzipped) in a directory,
    mailinglists from an xml or json file including metadata
    See http://docs.python.org/library/mailbox.html#mailbox.mbox
    """
    product = 'mbox'

    def import_project(self, sourcepath, destinationpath, name=None, **kwargs):
        threads = []
        mailinglist_xml_filename = os.path.join(sourcepath, 'mailinglist.xml')
        mailinglist_json_filename = os.path.join(sourcepath,'mailinglist.json')
        mapping_ini = os.path.join(sourcepath, 'target.ini')
        try:
            cp = ConfigParser()
            cp.read(mapping_ini)
            self.project_map = dict(cp.items('migrate'))
        except NoSectionError,e:
            self.project_map = {}        
        
        if os.path.exists(mailinglist_xml_filename):
            mlists = self.get_listdata_from_xml(mailinglist_xml_filename)
            self.xml_root = et.parse(mailinglist_xml_filename).getroot()
            name = self.project_map.get(self.xml_root.get('project'), name)
        elif os.path.exists(mailinglist_json_filename):
            mlists = self.get_listdata_from_xml(mailinglist_json_filename)
        else:
            entries = os.listdir(sourcepath)
            mlists = []
            for entry in entries:
                fullpath = os.path.join(sourcepath, entry)
                if not os.path.isfile(fullpath):
                    continue
                t = Thread(target=self.read_file, args=(fullpath, None))
                t.daemon = True
                t.start()            
                threads.append(t)
        if name is None:
            raise ValueError("No project to import.") 
      
        env_path = os.path.join(destinationpath, name)
        self.env = open_environment(env_path)        
        self.env.log.info('Importing from %s', sourcepath)
        for mlist in mlists:
            path = os.path.join(sourcepath, mlist.pop('mailbox'))
            if not os.path.exists(path):
                self.env.log.error("Can't find mailbox %s from %s", path, sourcepath)
                continue
            if mlist.get('mailboxmd5'):
                self.env.env.log.debug('Checking MD5 sum of %s...', path)
                md5digest = md5(open(path, 'r').read()).hexdigest()
                if md5digest != mlist['mailboxmd5']:
                    self.env.log.error("%s's md5 (%s) doesn't match %s from %s. Skipping it", path, md5digest, mlist['mailboxmd5'], sourcepath)
                    continue
                self.env.log.debug('MD5 of %s ok', path)
            else:
                self.env.log.warning("No md5 found for %s in %s", path, sourcepath)
            t = Thread(target=self.read_file, args=(path, mlist))
            t.daemon = True
            t.start()            
            threads.append(t)
        for t in threads:
            t.join()

    def get_listdata_from_xml(self, sourcefile):
        xml = et.ElementTree()
        xml.parse(sourcefile)
        for mlist in xml.findall('mailinglist'):
            attr = mlist.attrib
            attr['date'] = parse_date(attr['date'],utc )
            attr['private'] = to_bool(attr['private'])
            attr['subscribers'] = []
            for sub in mlist.findall('subscriber'):
                subinfo = sub.attrib
                for key in 'poster gposter decline'.split():
                    subinfo[key] = to_bool(subinfo[key])
                subinfo['groups'] = []
                for group in sub.findall('group'):
                    subinfo['groups'].append(group.attr['groupname'])
                attr['subscribers'].append(subinfo)
            yield attr
    
    def get_listdata_from_json(self, sourcefile):
        lists = json.load(open(sourcefile))
        for mlist in lists:
            mlist['date'] = parse_date(mlist['date'])
            yield mlist
    
    def read_file(self, mbox_file, metadata=None):
                         
        mailinglist_name = os.path.basename(mbox_file).rstrip('mbox.gz')
        date = datetime.utcnow()
        date = date.replace(tzinfo=utc)
        if not metadata:
            metadata = dict(emailaddress=mailinglist_name,
                            name='%s (Imported)' % mailinglist_name,
                            private=True,
                            postperm='MEMBERS',
                            replyto='LIST',
                            date=date,
                            individuals=[],
                            groups=[],
                            declines=[])
        individuals = metadata.pop('individuals','')
        groups = metadata.pop('groups','')
        subscribers = metadata.pop('subscribers', [])
        declines = metadata.pop('declines','')
        
        try:
            mailinglist = Mailinglist.select_by_address(self.env, mailinglist_name, localpart=True)
        except ResourceNotFound:
            mailinglist = Mailinglist(self.env, **metadata)
            try:
                mailinglist.insert()
            except Exception, e:
                self.env.log.exception(metadata)
                raise
        
        group_subscriptions = list(mailinglist.groups())
        individual_subscriptions = list(mailinglist.individuals())
        declined_subscriptions = list(mailinglist.declines())
        
        for group in groups:
            if (group['name'], group['poster']) not in group_subscriptions:
                mailinglist.subscribe(group=group['name'], poster=group['poster'])
       
        for individual in individuals:
            if (individual['name'], individual['poster']) not in individual_subscriptions:
                mailinglist.subscribe(user=individual['name'], poster=individual['poster'])
       
        for user in declines:
            if user not in declined_subscriptions:
                mailinglist.unsubscribe(user=user)
       
        if mbox_file.endswith('.gz'):
            fp, path = tempfile.mkstemp()
            tmpfile = path
            try:
                os.write(fp, gzip.open(mbox_file, 'rb').read())
            except IOError:
                self.env.log.exception('Failed to write %s from %s', path, mbox_file)
                os.unlink(tmpfile)
                return
            else:
                os.close(fp)
        else:
            path = mbox_file
            tmpfile = None
        self.env.log.info('Importing mbox %s', mbox_file)
               
        mbox = mailbox.mbox(path)
        inserted = 0
        errors = 0
        for mail in mbox:
            try_cnt = 5
            while try_cnt > 0:
                try:
                    msg = mail.as_string()
                    try:
                        msg = msg.encode('utf-8')
                    except UnicodeEncodeError:
                        msg = msg.encode('iso-8859-15')
                    mailinglist.insert_raw_email(msg)
                    inserted += 1
                    break
                except Exception, e:
                    # Don't import specific OperatinalError (pg/sqlite)
                    if e.__class__.__name__ == 'OperationalError':
                        # Only retry when we have a db failure, might for instance be failure to get file lock in sqlite
                        if try_cnt > 1:
                            self.env.log.exception("Failed to insert message, retry %d/5", 6-try_cnt)
                            try_cnt -= 1
                            time.sleep(0.5)
                        else:
                            self.env.log.exception('Stop retrying')
                            errors += 1
                            break
                    else:
                        self.env.log.exception('Failed to insert message')
                        errors += 1
                        break
        self.env.log.info('%s: Inserted %d/%d messages', mbox_file, inserted, inserted+errors)
        if tmpfile:
            os.unlink(tmpfile)
