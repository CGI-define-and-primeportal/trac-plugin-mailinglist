from trac.wiki.macros import WikiMacroBase
from trac.wiki.api import parse_args
from trac.wiki.formatter import system_message
from trac.resource import ResourceSystem, Resource, ResourceNotFound, get_resource_url
from trac.util.datefmt import format_datetime, pretty_timedelta

from genshi.builder import tag

from mailinglistplugin.api import MailinglistSystem
from mailinglistplugin.model import Mailinglist, MailinglistConversation, MailinglistMessage
from mailinglistplugin.utils import wrap_and_quote

class MailinglistMacro(WikiMacroBase):
    """Show a list of the available mailinglists:

   `[[Mailinglist]]`

Show a list of the recent messages to a particular mailinglist:

   `[[Mailinglist(`''mailinglist-name''`)]]`

Show a list of the recent '''20''' messages to a particular mailinglist:

   `[[Mailinglist(`''mailinglist-name''`,`'''20'''`)]]`

Show a list of the recent '''20''' messages to a particular mailinglist with subject contains '''bart''':

   `[[Mailinglist(`''mailinglist-name''`,limit=20, insubject=bart)]]`

Show the content of message:

   `[[Mailinglist(`''mailinglist-name''`/`''conversation number''`/`''message number''`)]]`

Another way, if your [http://trac-hacks.org/wiki/IncludeMacro IncludeMacro] is new enough, is to use the Include macro:

   `[[Include(mailinglist:`''mailinglist-name''`/`''conversation number''`/`''message number''`)]]`
   
Show the top '''5''' lines of content of message:

   `[[Mailinglist(`''mailinglist-name''`/`''conversation number''`/`''message number'','''5'''`)]]`
   
Some other possible ways to include mailinglist content in a page:

   `[[Image(`mailinglist:''mailinglist-name''`/`''conversation number''`/`''message number''`:`''filename.jpg''`)]]`

   `attachment:`''filename.jpg''`:mailinglist:`''mailinglist-name''`/`''conversation number''`/`''message number''

    """
    # IWikiMacroProvider methods
    def render_macro(self, req, name, content):
        args,kwargs = parse_args(content)
        if len(args) == 0:
            ul = tag.ul(class_="mailinglistlist")

            for mailinglist in Mailinglist.select(self.env):
                if "MAILINGLIST_VIEW" in req.perm(mailinglist.resource):         
                    ul.append(tag.li(tag.a(mailinglist.name,
                                           href=get_resource_url(self.env, mailinglist.resource, req.href))))
                        
            return ul
        if kwargs.has_key('limit'):
            limit = int(kwargs['limit'])
        elif len(args) > 1:
            limit = int(args[1])
        else:
            limit = 10
        resource = Resource("mailinglist",args[0])
        instance = MailinglistSystem(self.env).get_instance_for_resource(resource)

        if isinstance(instance, Mailinglist):
            if not req.perm(instance.resource).has_permission('MAILINGLIST_VIEW'):
                return system_message("Permission denied viewing mailinglist: %s" % instance.name)
            ul = tag.ul()
            for message in instance.messages(limit=limit, insubject=kwargs.get('insubject', None),desc=True):
                ul.append(tag.li(
                    tag.a(tag.span(message.subject, class_="messagesubject"),
                          href=get_resource_url(self.env, message.resource, req.href)),
                    " (",
                    tag.span(pretty_timedelta(message.date), class_="messageage"),
                    " ago)"))
            ul.append(tag.li(tag.a("(%d messages...)" % instance.count_messages(insubject=kwargs.get('insubject', None)),
                                   href=get_resource_url(self.env, instance.resource, req.href))))
            return tag.div("Mailinglist: ",
                           tag.a(instance.name,
                                 href=get_resource_url(self.env, instance.resource, req.href)),
                           ul,
                           class_="mailinglistfeed")
        elif isinstance(instance, MailinglistMessage):
            if not req.perm(instance.resource).has_permission('MAILINGLIST_VIEW'):
                return system_message("Permission denied viewing mail.")


            else:
                limit = None
            text = wrap_and_quote(instance.body, 78)[0]
            if limit:
                text = "\n".join(text.split("\n")[0:limit])
                textelement = tag.pre(text) + tag.a(tag.pre("(More...)"),
                                                    href=get_resource_url(self.env, instance.resource, req.href))
            else:
                textelement = tag.pre(text)                
            return tag.div(
                tag.div("Mailinglist: ",
                        tag.a(instance.conversation.mailinglist.name,
                              href=get_resource_url(self.env, instance.conversation.mailinglist.resource, req.href))),
                tag.div("Subject: ",
                        tag.a(instance.subject, href=get_resource_url(self.env, instance.resource, req.href))),
                tag.div("From: ",
                        tag.a(instance.from_name, href="mailto:%s" % instance.from_email)),
                tag.div("To: ", instance.to_header),
                tag.div("Date: %s" % format_datetime(instance.date, tzinfo=req.tz)),
                tag.div(textelement),
                class_="mailinglistmessage")            
            
        return system_message("Unknown Mailinglist: %s" % content)
    
