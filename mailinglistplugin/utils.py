import email
import email.Header
from email import Charset
from email.MIMEText import MIMEText
from email.MIMEMultipart import MIMEMultipart
from email.Utils import formatdate, make_msgid

from datetime import datetime
import re

from trac.util.datefmt import utc, to_timestamp

def wrap_and_quote(text, width):
    text = re.sub('(\n *){3,}', '\n\n', text)
    idx = text.find('________________________________\n\nFr')
    if idx == -1:
        idx = text.find('-----Original Message-----\nFr')
    if idx == -1:
        idx = text.find('-----Ursprungligt meddelande-----\nFr')
    if idx == -1:
        idx = text.find('Please help Logica to respect the environment by not printing this email')
        
    if idx > 20:
        return wrap(text[:idx], width), wrap(text[idx:], width)
    else:
        return wrap(text, width), ''

# from: http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/148061
def wrap(text, width):
    """
    A word-wrap function that preserves existing line breaks
    and most spaces in the text. Expects that existing line
    breaks are posix newlines (\n).
    """
    return reduce(lambda line, word, width=width: '%s%s%s' %
                  (line,
                   ' \n'[(len(line)-line.rfind('\n')-1
                          + len(word.split('\n',1)[0]
                                ) >= width)],
                   word),
                  text.split(' ')
                  )

_r1 = re.compile('-{2,}')
_r2 = re.compile('_{2,}')
_r3 = re.compile('={2,}')
def sanetize_text(text):
    """
    Sanetizes text by shortening overly long '--','__' and '==' sequences.
    """
    return _r1.sub('--', _r2.sub('__', _r3.sub('==', text)))

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
