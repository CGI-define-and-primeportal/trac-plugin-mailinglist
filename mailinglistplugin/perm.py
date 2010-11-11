from trac.perm import IPermissionRequestor, IPermissionPolicy
from trac.core import Component, implements, TracError, Interface, ExtensionPoint

from mailinglistplugin.model import Mailinglist, Mailinglist

class MailinglistPermissionPolicy(Component):
    implements(IPermissionPolicy)

    # IPermissionPolicy methods
    def check_permission(self, action, username, resource, perm):
        self.log.debug("Checking if %s can do %s on %s", action, username, resource)
        if action is "MAILINGLIST_VIEW":
            if resource.realm == "mailinglist":
                if "TRAC_ADMIN" in perm:
                    return True
                mailinglist = Mailinglist(self.env, resource.id)
                if mailinglist.private == False:
                    return None # it's up to the general permissions table
                elif mailinglist.private == True:
                    return username in mailinglist.subscribers()
            
        if action is "MAILINGLIST_POST":
            if resource is None:
                # In general, people can post...
                return True
            if resource.realm == "mailinglist":
                mailinglist = Mailinglist(self.env, resource.id)
                if mailinglist.postperm == "OPEN":
                    return True
                elif mailinglist.postperm == "RESTRICTED":
                    try:
                        return mailinglist.subscribers()[username]['poster']
                    except KeyError, e:
                        return False
                elif mailinglist.postperm == "MEMBERS":
                    return username in mailinglist.subscribers()
