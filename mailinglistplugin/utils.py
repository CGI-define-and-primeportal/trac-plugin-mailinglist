import email
import email.Header
from email import Charset
from email.MIMEText import MIMEText
from email.MIMEMultipart import MIMEMultipart
from email.Utils import formatdate, make_msgid

from datetime import datetime

from trac.util.datefmt import utc, to_timestamp

def encode_header(value, charset=None):
    """
    Encodes mail headers.

    If `value` is a list each list item will be encoded separately and
    returned as a comma separated list.
    If `value` is a tuple it will be interpreted as (name, email).
    """
    if isinstance(value, list):
        return ', \n\t'.join([encode_header(v, charset)
                              for v in value])
    elif isinstance(value, tuple):
        return '%s <%s>' % (email.Header.Header(value[0], charset), value[1])
    else:
        return email.Header.Header(value, charset).encode()

def decode_header(text):
        """
        Decode a header value and return the value as a unicode string.
        """
        if not text:
            return text
        res = []
        for part, charset in email.Header.decode_header(text):
            res.append(unicode(part, charset and charset or 'ascii', 'ignore'))
        return ' '.join(res)

def parse_rfc2822_date(text):
    """
    Parse an rfc2822 date string into a datetime object.
    """
    t = email.Utils.mktime_tz(email.Utils.parsedate_tz(text))
    return datetime.fromtimestamp(t, utc)
