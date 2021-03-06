# Copyright (c) 2015 CGI
# 
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 
#     * Redistributions of source code must retain the above copyright 
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of CGI nor the names of its
#       contributors may be used to endorse or promote products derived from
#       this software without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# ----------------------------------------------------------------------------

from setuptools import setup

setup(
    name = 'MailinglistPlugin',
    version = '0.1',
    author = 'Nick Piper',
    author_email = 'nick.piper@cgi.com',
    maintainer="CGI CoreTeam",
    maintainer_email="coreteam.service.desk.se@cgi.com",
    contact="CGI CoreTeam",
    contact_email="coreteam.service.desk.se@cgi.com",
    classifiers=['License :: OSI Approved :: BSD License'],
    license='BSD',
    url='http://define.primeportal.com/',
    description = 'Mailing list archive.',
    packages = ['mailinglistplugin'],
    package_data = {'mailinglistplugin': [
        'templates/*.html',
        'htdocs/*.js',
        'htdocs/css/*.css',
        'htdocs/*.png']
    },
    entry_points = {
        'define.importers': [
            'mbox = mailinglistplugin.importers:mbox_to_mailinglist_importer',
            'maildir = mailinglistplugin.importers:maildir_to_mailinglist_importer',
            ],
        'trac.plugins': [
            'mailinglistplugin.api = mailinglistplugin.api',
            'mailinglistplugin.admin = mailinglistplugin.admin',            
            'mailinglistplugin.model = mailinglistplugin.model',
            'mailinglistplugin.perm = mailinglistplugin.perm',
            'mailinglistplugin.web_ui = mailinglistplugin.web_ui',
            'mailinglistplugin.macros = mailinglistplugin.macros',
            ]},
    install_requires = ['Trac>=0.12', 'Genshi>=0.5', 'AnnouncerPlugin',
                        ],
    tests_require = ['nose'],
    test_suite = 'nose.collector',
)
