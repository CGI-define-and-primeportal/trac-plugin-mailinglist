from threading import Thread
from Queue import Queue
import gzip
import os
import mailbox
import time
import tempfile
from trac.env import open_environment
from trac.resource import ResourceNotFound
from trac.config import _TRUE_VALUES
from mailinglistplugin.model import Mailinglist
from dateutil.parser import parse as parse_date
from datetime import datetime
try:
    from xml.etree import ElementTree as et
    import json
    from hashlib import md5
except ImportError:
    from elementtree import ElementTree as et
    import simplejson as json
    from md5 import new as md5
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
            raise KeyError("This importer requires a Trac project to already exist. Use --name to specify its dir name.")
        
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
        if name is None:
            raise KeyError("This importer requires a Trac project to already exist. Use --name to specify it's dir name.")
        boxqueue = Queue()
        env_path = os.path.join(destinationpath, name)
        self.env = open_environment(env_path)
        import logging
        self.env.log.setLevel(logging.WARNING)
        self.log = logging.getLogger(self.env.path + '.' + self.__class__.__name__)
        self.log.setLevel(logging.DEBUG)
        
        if os.path.isdir(sourcepath):
            self.log.info('Importing directory %s', sourcepath)
            entries = os.listdir(sourcepath)
            for entry in entries:
                fullpath = os.path.join(sourcepath, entry)
                if not os.path.isfile(fullpath):
                    continue
                boxqueue.put((fullpath, None))
        else:
            self.log.info('Importing from %s', sourcepath)
            if sourcepath.endswith('.xml'):
                mlists = self.get_listdata_from_xml(sourcepath)
            elif sourcepath.endswith('.json'):
                mlists = self.get_listdata_from_json(sourcepath)
            importdir = os.path.dirname(sourcepath)
            for mlist in mlists:
                path = os.path.join(importdir, mlist.pop('mailbox'))
                if not os.path.exists(path):
                    self.log.error("Can't find mailbox %s from %s", path, sourcepath)
                    continue
                if mlist.get('mailboxmd5'):
                    self.log.debug('Checking MD5 sum of %s...', path)
                    md5digest = md5(open(path, 'r').read()).hexdigest()
                    if md5digest != mlist['mailboxmd5']:
                        self.log.error("%s's md5 (%s) doesn't match %s from %s. Skipping it", path, md5digest, mlist['mailboxmd5'], sourcepath)
                        continue
                    self.log.debug('MD5 of %s ok', path)
                else:
                    self.log.warning("No md5 found for %s in %s", path, sourcepath)
                boxqueue.put((path, mlist))
            else:
                boxqueue.put((sourcepath, None))
        def worker(queue):
            while True:
                mbox, metadata = queue.get()
                try:
                    self.read_file(mbox, metadata)
                except:
                    self.log.exception("Error in %s", mbox)
                queue.task_done()
        for _ in range(min(boxqueue.qsize(), 5)):
            t = Thread(target=worker, args=(boxqueue,))
            t.daemon = True
            t.start()
        boxqueue.join()

    def get_listdata_from_xml(self, sourcefile):
        xml = et.ElementTree()
        xml.parse(sourcefile)
        for mlist in xml.findall('mailinglist'):
            attr = mlist.attrib
            attr['date'] = parse_date(attr['date'])
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
        if not metadata:
            metadata = dict(emailaddress=mailinglist_name,
                            name='%s (Imported)' % mailinglist_name,
                            private=True,
                            postperm='MEMBERS',
                            replyto='LIST',
                            date=datetime.utcnow(),
                            individuals=[],
                            groups=[],
                            declines=[])
        individuals = metadata.pop('individuals')
        groups = metadata.pop('groups')
        declines = metadata.pop('declines')
        try:
            mailinglist = Mailinglist.select_by_address(self.env, mailinglist_name, localpart=True)
        except ResourceNotFound:
            mailinglist = Mailinglist(self.env, **metadata)
            try:
                mailinglist.insert()
            except Exception, e:
                self.log.exception(metadata)
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
                self.log.exception('Failed to write %s from %s', path, mbox_file)
                os.unlink(tmpfile)
                return
            finally:
                os.close(fp)
        else:
            path = mbox_file
            tmpfile = None
        self.log.info('Importing mbox %s', mbox_file)
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
                            self.log.exception("Failed to insert message, retry %d/5", 6-try_cnt)
                            try_cnt -= 1
                            time.sleep(0.5)
                        else:
                            self.log.exception('Stop retrying')
                            errors += 1
                            break
                    else:
                        self.log.exception('Failed to insert message')
                        errors += 1
                        break
        self.log.info('%s: Inserted %d/%d messages', mbox_file, inserted, inserted+errors)
        if tmpfile:
            os.unlink(tmpfile)
