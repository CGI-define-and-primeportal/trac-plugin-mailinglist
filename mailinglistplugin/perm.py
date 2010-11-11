from trac.perm import IPermissionRequestor, IPermissionPolicy
from trac.core import Component, implements, TracError, Interface, ExtensionPoint

from mailinglistplugin.api import MailinglistSystem

class MailinglistPermissionPolicy(Component):
    implements(IPermissionPolicy)

    # IPermissionPolicy methods
    def check_permission(self, action, username, resource, perm):
        if action is "ATTACHMENT_VIEW":
            self.log.debug("Deciding if %s can do %s on %s", username, action, resource)
            if resource.parent.realm == "mailinglist":
                message = MailinglistSystem(self.env).get_instance_for_resource(resource.parent)
                return "MAILINGLIST_VIEW" in perm(message.conversation.mailinglist.resource)

        elif action is "MAILINGLIST_VIEW":
            self.log.debug("Deciding if %s can do %s on %s", username, action, resource)
            if resource.realm == "mailinglist":
                if "TRAC_ADMIN" in perm:
                    return True
                mailinglist = MailinglistSystem(self.env).get_instance_for_resource(resource)
                if mailinglist.private == False:
                    return None # it's up to the general permissions table
                elif mailinglist.private == True:
                    return username in mailinglist.subscribers()
            
        elif action is "MAILINGLIST_POST":
            self.log.debug("Deciding if %s can do %s on %s", username, action, resource)            
            if resource is None:
                # In general, people can post...
                return True
            if resource.realm == "mailinglist":
                mailinglist = MailinglistSystem(self.env).get_instance_for_resource(resource)
                if mailinglist.postperm == "OPEN":
                    return True
                elif mailinglist.postperm == "RESTRICTED":
                    try:
                        return mailinglist.subscribers()[username]['poster']
                    except KeyError, e:
                        return False
                elif mailinglist.postperm == "MEMBERS":
                    return username in mailinglist.subscribers()
