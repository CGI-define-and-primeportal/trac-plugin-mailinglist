from trac.mimeview.api import Mimeview, IContentConverter, Context
from trac.core import Component, implements
from trac.perm import IPermissionRequestor
from trac.resource import Resource, IResourceManager, get_resource_url
from trac.config import BoolOption, IntOption, ListOption
from trac.web.chrome import INavigationContributor, ITemplateProvider, \
                            add_stylesheet, add_link, add_ctxtnav, prevnext_nav
from trac.web.main import IRequestHandler
from trac.timeline.api import ITimelineEventProvider
from trac.util.translation import _
from trac.attachment import Attachment, AttachmentModule
from trac.util.compat import any, partial

import re
from genshi.builder import tag

from mailinglistplugin.model import Mailinglist, MailinglistConversation, MailinglistMessage
from mailinglistplugin.utils import wrap_and_quote

import pkg_resources

class MailinglistModule(Component):
    implements(IRequestHandler, ITemplateProvider, INavigationContributor)

    limit = IntOption("mailinglist", "page_size", 20,
                      "Number of conversations to show per page")
    
    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        return []

    def get_templates_dirs(self):
        return [pkg_resources.resource_filename(__name__, 'templates')]

    # INavigationContributor methods
    def get_active_navigation_item(self, req):
        return 'mailinglist'

    def get_navigation_items(self, req):
        yield ('mainnav', 'mailinglist',
               tag.a(_('Mailinglist'), href=req.href.mailinglist()))

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
        
        mailinglists = [m for m in Mailinglist.select(self.env)
                        if "MAILINGLIST_VIEW" in req.perm(m.resource)]

        data = {"mailinglists": mailinglists,
                "offset": offset,
                "limit": self.limit,
                "wrap_and_quote": wrap_and_quote}

        #for mailinglist in mailinglists:
        #    add_ctxtnav(req,
        #                _("List: %s") % mailinglist.name,
        #                req.href.mailinglist(mailinglist.emailaddress))
        
        if 'messageid' in req.args:
            message = MailinglistMessage(self.env, req.args['messageid'])

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
            return 'mailinglist_list.html', data, None
    
