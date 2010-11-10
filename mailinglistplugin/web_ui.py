from trac.core import Component, implements
from trac.perm import IPermissionRequestor
from trac.resource import Resource, IResourceManager
from trac.config import BoolOption, IntOption, ListOption
from trac.web.chrome import INavigationContributor, ITemplateProvider, \
                            add_stylesheet, add_link
from trac.web.main import IRequestHandler
from trac.timeline.api import ITimelineEventProvider
from trac.util.translation import _

from genshi.builder import tag

from mailinglistplugin.model import Mailinglist

import pkg_resources

class MailinglistModule(Component):
    implements(IRequestHandler, ITemplateProvider, INavigationContributor)
    
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
            return True

    def process_request(self, req):

        mailinglists = []
        for mailinglist in Mailinglist.select(self.env):
            if "MAILINGLIST_VIEW" in req.perm(mailinglist.resource):
                mailinglists.append(mailinglist)
                
        data = {
            "mailinglists": mailinglists,
            }
        
        return 'mailinglist_list.html', data, None
    
