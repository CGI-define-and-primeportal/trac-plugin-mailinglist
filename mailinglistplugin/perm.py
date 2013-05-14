from trac.perm import IPermissionRequestor, IPermissionPolicy
from trac.core import Component, implements, TracError, Interface, ExtensionPoint

from mailinglistplugin.api import MailinglistSystem
from mailinglistplugin.model import MailinglistConversation, MailinglistMessage

class MailinglistPermissionPolicy(Component):
    implements(IPermissionPolicy)

    # IPermissionPolicy methods
    def check_permission(self, action, username, resource, perm):

        # maybe we need to reorganise a little, to factor up the
        # "isinstance" business.
        
        if action is "ATTACHMENT_VIEW":
            self.log.debug("Deciding if %s can do %s on %s", username, action, resource)
            if resource and resource.parent and resource.parent.realm == "mailinglist":
                return "MAILINGLIST_VIEW" in perm(resource.parent)

        elif action is "MAILINGLIST_VIEW":
            self.log.debug("Deciding if %s can do %s on %s", username, action, resource)
            # if no resource, then it's up to the general permissions table
            if resource and resource.realm == "mailinglist":
                instance = MailinglistSystem(self.env).get_instance_for_resource(resource)
                if isinstance(instance, MailinglistMessage):
                    return action in perm(instance.conversation.resource)
                elif isinstance(instance, MailinglistConversation):
                    return action in perm(instance.mailinglist.resource)
                elif instance.private == False:
                    # it's a mailinglist
                    return None # it's up to the general permissions table
                elif instance.private == True:
                    # it's a mailinglist
                    return username in instance.subscribers()
            
        elif action is "MAILINGLIST_POST":
            self.log.debug("Deciding if %s can do %s on %s", username, action, resource)            
            if resource is None:
                # In general, people can post...
                return True
            if resource.realm == "mailinglist":
                instance = MailinglistSystem(self.env).get_instance_for_resource(resource)
                if isinstance(instance, MailinglistMessage):
                    return action in perm(instance.conversation.resource)
                elif isinstance(instance, MailinglistConversation):
                    return action in perm(instance.mailinglist.resource)
                elif instance.postperm == "OPEN":
                    return True
                elif instance.postperm == "RESTRICTED":
                    try:
                        return instance.subscribers()[username]['poster']
                    except KeyError, e:
                        return False
                elif instance.postperm == "MEMBERS":
                    return username in instance.subscribers()
