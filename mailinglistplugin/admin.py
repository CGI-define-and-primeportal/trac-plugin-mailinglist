from trac.core import Component, implements, TracError
from trac.util.compat import partial
from trac.web.chrome import ITemplateProvider, add_stylesheet, add_script
from trac.admin.api import IAdminPanelProvider
from trac.web.chrome import Chrome, add_notice, add_warning
from trac.util.translation import _
from trac.resource import ResourceNotFound
from mailinglistplugin.api import MailinglistSystem
from mailinglistplugin.model import Mailinglist, MailinglistConversation, MailinglistMessage

class MailinglistAdmin(Component):

    implements(ITemplateProvider, IAdminPanelProvider)


    # IAdminPanelProvider methods
    
    def get_admin_panels(self, req):
        if 'MAILINGLIST_ADMIN' in req.perm:
            yield ('mailinglist', 'Mailing List', 'lists', 'Lists') 

    def render_admin_panel(self, req, cat, page, mailinglist_emailpart):
        req.perm.require('MAILINGLIST_ADMIN')

        if mailinglist_emailpart:
            mailinglist = Mailinglist.select_by_address(self.env,
                                                        mailinglist_emailpart,
                                                        localpart=True)
            if req.method == 'POST':
                if req.args.get('save'):
                    mailinglist.name = req.args.get('name')
                    mailinglist.private = req.args.get('private') == 'PRIVATE'
                    mailinglist.postperm = req.args.get('postperm')
                    mailinglist.replyto = req.args.get('replyto')
                    mailinglist.description = req.args.get('description')
                    if 'TRAC_ADMIN' in req.perm:
                        mailinglist.emailaddress = req.args.get('emailaddress')
                    mailinglist.save_changes()
                    add_notice(req, _('Your changes have been saved.'))
                    req.redirect(req.href.admin(cat, page))
                elif req.args.get('cancel'):
                    req.redirect(req.href.admin(cat, page))
                elif req.args.get('subscribeuser'):
                    @self.env.with_transaction()
                    def do_subscribe(db):
                        mailinglist = Mailinglist.select_by_address(self.env, mailinglist_emailpart,
                                                                    localpart=True, db=db)
                        mailinglist.subscribe(user=req.args['username'], db=db)
                    add_notice(req, _('The user %s has been subscribed.') % req.args['username'])
                    
                    req.redirect(req.href.admin(cat, page, mailinglist_emailpart))
                elif req.args.get('removeusers'):
                    sel = req.args.get('sel')
                    if not sel:
                        raise TracError(_('No users selected'))
                    if not isinstance(sel, list):
                        sel = [sel]
                    @self.env.with_transaction()
                    def do_remove(db):
                        mailinglist = Mailinglist.select_by_address(self.env, mailinglist_emailpart,
                                                                    localpart=True, db=db)
                        for username in sel:
                            mailinglist.unsubscribe(user=username, db=db)
                    add_notice(req, _('The selected users have been unsubscribed.'))
                    
                    req.redirect(req.href.admin(cat, page, mailinglist_emailpart))
                elif req.args.get('subscribegroup'):
                    @self.env.with_transaction()
                    def do_subscribe(db):
                        mailinglist = Mailinglist.select_by_address(self.env, mailinglist_emailpart,
                                                                    localpart=True, db=db)
                        mailinglist.subscribe(group=req.args['groupname'], db=db)
                    add_notice(req, _('The group %s has been subscribed.') % req.args['groupname'])
                    
                    req.redirect(req.href.admin(cat, page, mailinglist_emailpart))                    
                elif req.args.get('removegroups'):
                    sel = req.args.get('sel')
                    if not sel:
                        raise TracError(_('No groups selected'))
                    if not isinstance(sel, list):
                        sel = [sel]
                    @self.env.with_transaction()
                    def do_remove(db):
                        mailinglist = Mailinglist.select_by_address(self.env, mailinglist_emailpart,
                                                                    localpart=True, db=db)
                        for username in sel:
                            mailinglist.unsubscribe(group=username, db=db)
                    add_notice(req, _('The selected groups have been unsubscribed.'))
                    
                    req.redirect(req.href.admin(cat, page, mailinglist_emailpart))
                elif req.args.get('updatepostergroups') or req.args.get('updateposterusers'):
                    sel = req.args.get('sel')
                    if not sel:
                        sel = []
                    if not isinstance(sel, list):
                        sel = [sel]
                    @self.env.with_transaction()
                    def do_update(db):
                        mailinglist = Mailinglist.select_by_address(self.env, mailinglist_emailpart,
                                                                    localpart=True, db=db)
                        if req.args.get('updatepostergroups'):
                            current_statuses =  mailinglist.groups()
                        else:
                            current_statuses =  mailinglist.individuals()
                        for subname, poster in current_statuses:
                            if req.args.get('updatepostergroups'):                            
                                updater = partial(mailinglist.update_poster, group=subname)
                            else:
                                updater = partial(mailinglist.update_poster, user=subname)                            
                            if poster and subname not in sel:
                                updater(poster=False)
                            elif not poster and subname in sel:
                                updater(poster=True)
                            
                    add_notice(req, _('Posters have been updated.'))
                    
                    req.redirect(req.href.admin(cat, page, mailinglist_emailpart))
                    

            Chrome(self.env).add_wiki_toolbars(req)

            if self.env.is_component_enabled('simplifiedpermissionsadminplugin.simplifiedpermissions.SimplifiedPermissions'):
                from simplifiedpermissionsadminplugin.simplifiedpermissions import SimplifiedPermissions
                # groups is used for subscription, so it should not have subscribed groups in it
                groups = set(SimplifiedPermissions(self.env).groups) - set([subscribed_group for subscribed_group, group_poster in mailinglist.groups()])
            else:
                groups = None
            
            data = {'view': 'detail',
                    'mailinglist': mailinglist,
                    'groups': groups,
                    'email_domain': MailinglistSystem(self.env).email_domain}
        else:
            if req.method == 'POST':
                if req.args.get('add') and req.args.get('emailaddress'):
                    emailaddress = req.args['emailaddress'].lower()
                    try:
                        mailinglist = Mailinglist.select_by_address(self.env, emailaddress, localpart=True)
                    except ResourceNotFound:
                        mailinglist = Mailinglist(self.env, name=req.args['name'])
                        mailinglist.private = req.args.get('private') == 'PRIVATE'
                        mailinglist.postperm = req.args.get('postperm')
                        mailinglist.replyto = req.args.get('replyto')
                        mailinglist.emailaddress = req.args.get('emailaddress')
                        mailinglist.insert()
                        add_notice(req, _('The mailinglist "%(addr)s" has been '
                                          'added.', addr=mailinglist.addr()))
                        req.redirect(req.href.admin(cat, page))
                    else:
                        raise TracError(_('Mailinglist with email address %(emailaddress)s already exists.',
                                          emailaddress=emailaddress))
                # Remove mailinglists
                elif req.args.get('remove'):
                    req.perm.require('TRAC_ADMIN')
                    sel = req.args.get('sel')
                    if not sel:
                        raise TracError(_('No mailinglist selected'))
                    if not isinstance(sel, list):
                        sel = [sel]
                    @self.env.with_transaction()
                    def do_remove(db):
                        for email in sel:
                            mailinglist = Mailinglist.select_by_address(self.env, email,
                                                                        localpart=True, db=db)
                            mailinglist.delete(db=db)
                    add_notice(req, _('The selected mailinglists have been '
                                      'removed.'))
                    req.redirect(req.href.admin(cat, page))
                    
                    
            mailinglists = Mailinglist.select(self.env)
            
            data = {'view': 'list',
                    'mailinglists': mailinglists,
                    'email_domain': MailinglistSystem(self.env).email_domain}                    
            
        return ('mailinglist_admin.html', data)

    # ITemplateProvider methods
    def get_templates_dirs(self):
        from pkg_resources import resource_filename
        return [resource_filename(__name__, 'templates')]

    def get_htdocs_dirs(self):
        from pkg_resources import resource_filename
        return [('mailinglist', resource_filename(__name__, 'htdocs'))]
