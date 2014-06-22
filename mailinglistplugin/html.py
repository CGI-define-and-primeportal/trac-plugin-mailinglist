"""
Genshi Transformers useful for HTML Mailing list messages
"""

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
