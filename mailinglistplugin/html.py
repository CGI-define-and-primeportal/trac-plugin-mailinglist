"""
Genshi Transformers useful for HTML Mailing list messages
"""

from trac.attachment import Attachment
from trac.resource import get_resource_url, ResourceNotFound

from genshi.core import Attrs, QName
from genshi.core import END, START, TEXT, COMMENT

OUTLOOK_QUOTE_SEP_STYLE = 'border:none; border-top:solid #B5C4DF 1.0pt; padding:3.0pt 0cm 0cm 0cm'

class RemoveOutlookQuotedMails(object):
    """
    It's rather hard to deal with the Outlook HTML message 'quoting'
    style, as they are not children of a well-specified div.

    Instead, there is a div with a particular border style which
    contains the "From" details (which are internationalised) - but
    this is a child of another div with no style - and the other parts
    of the message are siblings of that parent 'plain' div.

    Here we will attempt to 'cut out' everything after the special
    'from' div (taking care to still end any tags still open at this
    point) and move everything we cut to be children of a new div with
    a class we can use to know it's the quoted content.
    """

    def __call__(self, stream):
        skipped_starts = 0
        in_skipping = False
        quoted_messages = 0
        streambuffer = []

        for kind, data, pos in stream:

            if kind is TEXT:
                if in_skipping:
                    streambuffer.append((kind, data, pos))
                    continue
                else:
                    yield kind, data, pos

            elif kind is START:
                tag, attrs = data
                if tag == 'div' and attrs.get('style') == OUTLOOK_QUOTE_SEP_STYLE:
                    in_skipping = True
                    quoted_messages += 1
                if in_skipping:
                    skipped_starts += 1
                    streambuffer.append((kind, data, pos))
                    continue
                yield kind, data, pos

            elif kind is END:
                tag = data
                if in_skipping and skipped_starts > 0:
                    skipped_starts -= 1
                    streambuffer.append((kind, data, pos))
                    continue
                yield kind, data, pos

            elif kind is not COMMENT:
                yield kind, data, pos

        if streambuffer:
            yield START, (QName('div'), Attrs([(QName('class'), u'hidden quoted'),
                                               (QName('data-quotedmessages'), unicode(quoted_messages))])), None
            for kind, data, pos in streambuffer:
                yield kind, data, pos
            yield END, QName('div'), None

class ConvertImgSourcesFromCID(object):
    """Convert src attributes for images from the "cid" syntax to a
    URL to the attachment.  Uses the filename as the key rather than
    the "id" part of the cid syntax - maybe this is wrong. We don't
    store the "id" looking part of the attachment/image yet though so
    we couldn't look up the file based on this.
    """


    def __init__(self, href, env, resource):
        self.href = href
        self.env = env
        self.resource = resource

    def __call__(self, stream):
        for kind, data, pos in stream:
            if kind is START:
                tag, attrs = data
                if tag == 'img' and attrs.get('src', '').startswith("cid:"):
                    # this is a guess, I don't know the "cid" rules
                    # and I didn't look them up yet as I'm on a plane.
                    filename = attrs.get('src')[4:].split("@", 2)[0]
                    try:
                        attrs |= [(QName('src'), get_resource_url(self.env,
                                                                  Attachment(self.env, 
                                                                             self.resource.realm, 
                                                                             self.resource.id, 
                                                                             filename).resource,
                                                                  self.href,
                                                                  format="raw"))]
                    except ResourceNotFound:
                        self.env.log.warning("Didn't find attachment for %s and img tag attributes %s", 
                                             self.resource, attrs)
                    yield kind, (tag, attrs), pos
                    continue

            yield kind, data, pos
