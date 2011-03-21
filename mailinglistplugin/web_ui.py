from trac.mimeview.api import Mimeview, IContentConverter, Context
from trac.core import Component, implements
from trac.perm import IPermissionRequestor
from trac.resource import Resource, IResourceManager, get_resource_url, ResourceNotFound
from trac.config import BoolOption, IntOption, ListOption
from trac.web.chrome import INavigationContributor, ITemplateProvider, \
                            add_stylesheet, add_javascript, add_link, \
                            add_ctxtnav, prevnext_nav, add_notice
from trac.web.main import IRequestHandler
from trac.timeline.api import ITimelineEventProvider
from trac.util.translation import _
from trac.attachment import Attachment, AttachmentModule
from trac.util.compat import any, partial
from trac.wiki.api import IWikiSyntaxProvider
from trac.util.datefmt import format_datetime, utc, to_timestamp
from trac.search import ISearchSource, search_to_sql, shorten_result

from datetime import datetime
import re
from genshi.builder import tag

from mailinglistplugin.api import MailinglistSystem
from mailinglistplugin.model import Mailinglist, MailinglistConversation, MailinglistMessage

import pkg_resources

class MailinglistModule(Component):
    implements(IRequestHandler, ITemplateProvider, INavigationContributor,
               IWikiSyntaxProvider, ISearchSource, ITimelineEventProvider)

    limit = IntOption("mailinglist", "page_size", 20,
                      "Number of conversations to show per page")
    
    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        return [('mailinglist', pkg_resources.resource_filename(__name__, 'htdocs'))]

    def get_templates_dirs(self):
        return [pkg_resources.resource_filename(__name__, 'templates')]

    # INavigationContributor methods
    def get_active_navigation_item(self, req):
        return 'mailinglist'

    def get_navigation_items(self, req):
        yield ('mainnav', 'mailinglist',
               tag.a(_('Mailinglist'), href=req.href.mailinglist()))

    # IWikiSyntaxProvider
    def get_wiki_syntax(self):
        yield (r'\bmailinglist:(?P<list_id>\d+)\b', 
               lambda f, m, fm: self._format_link(f, 'mailinglist', 
                                                  fm.group('list_id'), 
                                                  m, fm))

    def get_link_resolvers(self):
        yield ('mailinglist', self._format_link)
    
    def _format_link(self, formatter, ns, target, label, match=None):
        resource = Resource('mailinglist', target)
        try:
            instance = MailinglistSystem(self.env).get_instance_for_resource(resource)
        except ResourceNotFound:
            return tag.a(label, class_='missing mailinglist')
        if isinstance(instance,Mailinglist):
            return tag.a("Mailinglist: %s" % instance.name, href=formatter.href.mailinglist(target))
        elif isinstance(instance,MailinglistConversation):
            return tag.a("%s: %s" % (instance.mailinglist.name, instance.subject),
                         href=formatter.href.mailinglist(target),
                         title="Dated %s" % format_datetime(instance.date, tzinfo=formatter.req.tz))
        elif isinstance(instance,MailinglistMessage):
            return tag.a("%s: %s" % (instance.conversation.mailinglist.name, instance.subject),
                         href=formatter.href.mailinglist(target),
                         title="Dated %s" % format_datetime(instance.date, tzinfo=formatter.req.tz))
        else:
            return tag.a(label, href=formatter.href.mailinglist(target))                    

    # ISearchSource methods

    def get_search_filters(self, req):
        if 'MAILINGLIST_VIEW' in req.perm:
            yield ('mailinglist', _("Mailinglist"))

    def get_search_results(self, req, terms, filters):
        if not 'mailinglist' in filters:
            return
        mailinglist_realm = Resource('mailinglist')

        lists = {}
        for mailinglist in Mailinglist.select(self.env):
            if "MAILINGLIST_VIEW" in req.perm(mailinglist.resource):         
                lists[mailinglist.id] = mailinglist
                
        if not lists:
            self.log.debug("This user can't view any lists, so not searching.")
            return
        
        db = self.env.get_read_db()
        sql, args = search_to_sql(db, ['subject','body','from_email','from_name'], terms)

        cursor = db.cursor()
        query = """
            SELECT id, subject, body, from_name, from_email, date, list, conversation
            FROM mailinglistmessages
            WHERE list IN (%s) AND %s
            """ % (",".join(map(str,lists.keys())), sql,)
        self.log.debug("Search query: %s", query)
        cursor.execute(query, args)
        for mid, subject, body, from_name, from_email, date, mlist, conversation in cursor:
            # build resource ourself to speed things up
            m = mailinglist_realm(id="%s/%d/%d" % (lists[mlist].emailaddress,
                                                   conversation,
                                                   mid))
            if 'MAILINGLIST_VIEW' in req.perm(m):
                yield (req.href.mailinglist(m.id),
                       tag("%s: %s" % (lists[mlist].name, subject)),
                       datetime.fromtimestamp(date, utc),
                       "%s <%s>" % (from_name, from_email),
                       shorten_result(body, terms))
        
        # Attachments
        for result in AttachmentModule(self.env).get_search_results(
            req, mailinglist_realm, terms):
            yield result        
        

    # IRequestHandler methods
    def match_request(self, req):
        if req.path_info.startswith("/mailinglist"):
            match = re.match(r'/mailinglist/([^/]+)$', req.path_info)
            if match:
                req.args['listname'] = match.group(1)
            match = re.match(r'/mailinglist/[^/]+/([0-9]+)$', req.path_info)
            if match:
                req.args['conversationid'] = match.group(1)
            match = re.match(r'/mailinglist/[^/]+/[0-9]+/([0-9]+)$', req.path_info)
            if match:
                req.args['messageid'] = match.group(1)
            return True

    def process_request(self, req):
        offset = int(req.args.get("offset",0))

        add_stylesheet(req, 'mailinglist/css/mailinglist.css')
        add_javascript(req, 'mailinglist/mailinglist.js')
            
        mailinglists = [m for m in Mailinglist.select(self.env)
                        if "MAILINGLIST_VIEW" in req.perm(m.resource)]

        data = {"mailinglists": mailinglists,
                "offset": offset,
                "limit": self.limit}

        #for mailinglist in mailinglists:
        #    add_ctxtnav(req,
        #                _("List: %s") % mailinglist.name,
        #                req.href.mailinglist(mailinglist.emailaddress))
        
        if 'messageid' in req.args:
            message = MailinglistMessage(self.env, req.args['messageid'])
            # leaks the subject of the email in the error, wonder if
            # that's a problem...
            req.perm(message.resource).require("MAILINGLIST_VIEW")
            if req.args.get('format') == "raw":
                req.send_header('Content-Disposition', 'attachment')
                req.send_response(200)
                content = message.raw.bytes
                req.send_header('Content-Type', 'application/mbox')
                req.send_header('Content-Length', len(content))
                req.end_headers()
                if req.method != 'HEAD':
                    req.write(content)
                return

            context = Context.from_request(req, message.resource)
            
            data['message'] = message
            data['attachments'] = AttachmentModule(self.env).attachment_data(context)

            add_link(req, 'up', get_resource_url(self.env, message.conversation.resource, req.href,
                                                 offset=data['offset']),
                     _("Back to conversation"))

            prevnext_nav(req, _("Newer message"), _("Older message"), 
                         _("Back to conversation"))

            raw_href = get_resource_url(self.env, message.resource,
                                        req.href, format='raw')
            add_link(req, 'alternate', raw_href, _('mbox'), "application/mbox")
            return 'mailinglist_message.html', data, None
            
        if 'conversationid' in req.args:
            conversation = MailinglistConversation(self.env, req.args['conversationid'])
            # also leaks the subject of the first email in the error message
            req.perm(conversation.resource).require("MAILINGLIST_VIEW")
            data['conversation'] = conversation
            data['attachmentselect'] = partial(Attachment.select, self.env)
            add_link(req, 'up', get_resource_url(self.env, conversation.mailinglist.resource, req.href,
                                                 offset=data['offset']),
                     _("List of conversations"))

            prevnext_nav(req, _("Newer conversation"), _("Older conversation"), 
                         _("Back to list of conversations"))
            
            return 'mailinglist_conversation.html', data, None
        elif 'listname' in req.args:
            mailinglist = Mailinglist.select_by_address(self.env,
                                                        req.args['listname'], localpart=True)
            # leaks the name of the mailinglist
            req.perm(mailinglist.resource).require("MAILINGLIST_VIEW")

            data['mailinglist'] = mailinglist

            if data['offset'] + data['limit'] < mailinglist.count_conversations():
                add_link(req, 'next',
                         get_resource_url(self.env, mailinglist.resource, req.href,
                                          offset=data['offset']+data['limit']),
                         _("Older conversations"))

            if offset > 0:
                add_link(req, 'prev',
                         get_resource_url(self.env, mailinglist.resource, req.href,
                                          offset=data['offset']-data['limit']),
                         _("Newer conversations"))

            add_link(req, 'up', req.href.mailinglist(), _("List of mailinglists"))

            prevnext_nav(req, _("Newer conversations"), _("Older conversations"), 
                         _("Back to Mailinglists"))

            return 'mailinglist_conversations.html', data, None
        else:
            if req.method == 'POST':
                mailinglist = Mailinglist.select_by_address(self.env,
                                                            req.args['listemailaddress'], localpart=True)
                req.perm(mailinglist.resource).require("MAILINGLIST_VIEW")
                if req.args.get('unsubscribe'):
                    mailinglist.unsubscribe(user=req.authname)
                    add_notice(req, _('You have been unsubscribed from %s.' % mailinglist.name))
                elif req.args.get('subscribe'):
                    mailinglist.subscribe(user=req.authname)
                    add_notice(req, _('You have been subscribed to %s.' % mailinglist.name))
                req.redirect(req.href.mailinglist())
                
            return 'mailinglist_list.html', data, None
    
    # ITimelineEventProvider methods

    def get_timeline_filters(self, req):
        if 'MAILINGLIST_VIEW' in req.perm:
            yield ('mailinglist', _("Mailinglist messages"))

    def get_timeline_events(self, req, start, stop, filters):
        if 'mailinglist' in filters:
            mailinglist_realm = Resource('mailinglist')

            lists = {}
            for mailinglist in Mailinglist.select(self.env):
                if "MAILINGLIST_VIEW" in req.perm(mailinglist.resource):         
                    lists[mailinglist.id] = mailinglist

            if not lists:
                self.log.debug("This user can't view any lists, so not listing timeline events.")
                return

            self.log.debug("Searching for timeline events in %s", lists)

            db = self.env.get_read_db()

            cursor = db.cursor()
            cursor.execute("SELECT id, subject, body, from_name, from_email, date, list, conversation "
                           "FROM mailinglistmessages "
                           "WHERE date>=%%s AND date<=%%s AND list IN (%s)" % ",".join(map(str,lists.keys())),
                           (to_timestamp(start), to_timestamp(stop)))
            # 
            for mid, subject, body, from_name, from_email, date, mlist, conversation in cursor:
                # build resource ourself to speed things up
                m = mailinglist_realm(id="%s/%d/%d" % (lists[mlist].emailaddress,
                                                       conversation,
                                                       mid))
                if 'MAILINGLIST_VIEW' in req.perm(m):
                    yield ('mailinglist', 
                           datetime.fromtimestamp(date, utc),
                           "%s <%s>" % (from_name, from_email),
                           (mid,
                            subject, 
                            body.lstrip()[:200],
                            lists[mlist].name, 
                            lists[mlist].emailaddress, 
                            conversation))

                # Attachments
                for event in AttachmentModule(self.env).get_timeline_events(
                    req, mailinglist_realm, start, stop):
                    yield event

    def render_timeline_event(self, context, field, event):
        mid, subject, snippet, listname, listemailaddress, conversation = event[3]
        if field == 'url':
            return context.href.mailinglist(listemailaddress, conversation, mid)
        elif field == 'title':
            return "%s: %s" % (listname, subject)
        elif field == 'description':
            return snippet

