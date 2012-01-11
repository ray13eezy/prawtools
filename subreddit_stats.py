#!/usr/bin/env python
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from optparse import OptionGroup, OptionParser
from reddit import Reddit
from urllib2 import HTTPError

DAYS_IN_SECONDS = 60 * 60 * 24


class SubRedditStats(object):
    VERSION = '0.1.dev'

    post_prefix = 'Subreddit Stats:'
    post_header = '### %s\n\n'
    post_footer = ('>Generated by **Subreddit Stats** written by '
                   '[bboe](/user/bboe)  \n'
                   '[Source available on github]'
                   '(https://github.com/bboe/subreddit_stats).  \n'
                   'Comments and suggestions are encouraged!  \n'
                   'Last message at: %d')
    re_marker = re.compile('Last message at: (\d+)')

    def __init__(self, site, verbosity):
        self.reddit = Reddit(str(self), site)
        self.verbosity = verbosity
        self.submissions = []
        self.comments = []
        self.submitters = defaultdict(list)
        self.commenters = defaultdict(list)
        self.min_date = 0
        self.max_date = time.time() - DAYS_IN_SECONDS * 3

    def __str__(self):
        return 'BBoe\'s SubRedditStats %s' % self.VERSION

    def login(self, user, pswd):
        if self.verbosity > 0:
            print 'Logging in'
        self.reddit.login(user, pswd)

    @staticmethod
    def _previous_max(submission):
        try:
            val = SubRedditStats.re_marker.findall(submission.selftext)[-1]
            return float(val)
        except (IndexError, TypeError):
            print 'End marker not found in previous submission. Aborting'
            sys.exit(1)

    def msg(self, msg, level):
        if self.verbosity >= level:
            print msg

    def fetch_recent_submissions(self, subreddit, since_last=True,
                                 max_duration=None):
        '''Fetches recent submissions in subreddit with boundaries.

        Does not include posts within the last three days as their scores may
        not be representative.

        Keyword arguments:
        subreddit -- the subreddit to retreive information from
        since_last -- boolean, if true use info from last submission to
                      determine stop point
        max_duration -- When set, specifies the number of days to include

        '''
        if max_duration:
            self.min_date = self.max_date - DAYS_IN_SECONDS * max_duration
        sub = self.reddit.get_subreddit(subreddit)
        self.msg('DEBUG: Fetching submissions', 1)
        for submission in sub.get_new_by_date(limit=None):
            if submission.created_utc > self.max_date:
                continue
            if submission.created_utc <= self.min_date:
                break
            if (since_last and str(submission.author) == str(self.reddit.user)
                and submission.title.startswith(self.post_prefix)):
                # Use info in this post to update the min_date
                # And don't include this post
                self.min_date = max(self.min_date,
                                    self._previous_max(submission))
                continue
            self.submissions.append(submission)
        self.msg('DEBUG: Found %d submissions' % len(self.submissions), 1)
        if len(self.submissions) == 0:
            return False

        # Update real min and max dates
        self.submissions.sort(key=lambda x: x.created_utc)
        self.min_date = self.submissions[0].created_utc
        self.max_date = self.submissions[-1].created_utc
        return True

    def process_submitters(self):
        self.msg('DEBUG: Processing Submitters', 1)
        for i, submission in enumerate(self.submissions):
            self.submitters[str(submission.author)].append(submission)
            self.msg('%d/%d submissions' % (i + 1, len(self.submissions)), 2)

    def process_commenters(self):
        self.msg('DEBUG: Processing Commenters', 1)
        for i, submission in enumerate(self.submissions):
            if submission.num_comments == 0:
                continue
            self.comments.extend(submission.all_comments_flat)
            for comment in self.comments:
                self.commenters[str(comment.author)].append(comment)
            self.msg('%d/%d submissions' % (i + 1, len(self.submissions)), 2)

    def basic_stats(self):
        sub_ups = sum(x.ups for x in self.submissions)
        sub_downs = sum(x.downs for x in self.submissions)
        comm_ups = sum(x.ups for x in self.comments)
        comm_downs = sum(x.downs for x in self.comments)

        values = [('Total', len(self.submissions), len(self.comments)),
                  ('Unique Redditors', len(self.submitters),
                   len(self.commenters)),
                  ('Upvotes', sub_ups, comm_ups),
                  ('Downvotes', sub_downs, comm_downs)]

        retval = self.post_header % 'Basic Stats'
        retval += '||Submissions|Comments|\n:--:|--:|--:\n'
        for triple in values:
            retval += '**%s**|%d|%d\n' % triple
        return '%s\n' % retval

    def top_submitters(self, num):
        num = min(num, len(self.submitters))
        if num <= 0:
            return ''

        top_submitters = sorted(self.submitters.items(), reverse=True,
                                key=lambda x: (sum(y.score for y in x[1]),
                                               len(x[1])))[:num]

        retval = self.post_header % 'Top Submitters'
        for i, (author, submissions) in enumerate(top_submitters):
            retval += '#### %d. [%s](/user/%s) (Score: %d)\n' % (
                i + 1, author, author, sum(x.score for x in submissions))
            for submission in sorted(submissions, key=lambda x: x.created_utc):
                if submission.permalink != submission.url:
                    link = ' ([External Link](%s))' % submission.url
                else:
                    link = ''
                retval += '* **%s** (Score: %d) ([Comments: %d](%s))%s\n' % (
                        submission.title, submission.score,
                        submission.num_comments, submission.permalink, link)
            retval += '\n'
        return '%s\n' % retval

    def top_commenters(self, num):
        score = lambda x: x.ups - x.downs

        num = min(num, len(self.commenters))
        if num <= 0:
            return ''

        top_commenters = sorted(self.commenters.items(), reverse=True,
                                key=lambda x: (sum(score(y) for y in x[1]),
                                               len(x[1])))[:num]

        retval = self.post_header % 'Top Commenters'
        for author, comments in top_commenters:
            retval += '1. [%s](/user/%s) Comments: %d (Score: %d)\n' % (
                author, author, len(comments), sum(score(x) for x in comments))
        return '%s\n' % retval

    def top_submissions(self, num):
        num = min(num, len(self.submissions))
        if num <= 0:
            return ''

        top_submissions = sorted(self.submissions, reverse=True,
                                 key=lambda x: x.score)[:num]

        retval = self.post_header % 'Top Submissions'
        for submission in top_submissions:
            if submission.permalink != submission.url:
                link = ' ([External Link](%s))' % submission.url
            else:
                link = ''
            retval += ('1. **%s** (Score: %d) ([Comments: %d](%s))%s '
                       '(by [%s](/user/%s))\n' % (
                    submission.title, submission.score,
                    submission.num_comments, submission.permalink, link,
                    str(submission.author), str(submission.author)))
        return '%s\n' % retval

    def top_comments(self, num):
        score = lambda x: x.ups - x.downs

        num = min(num, len(self.comments))
        if num <= 0:
            return ''

        top_comments = sorted(self.comments, reverse=True,
                                 key=score)[:num]
        retval = self.post_header % 'Top Comments'
        for comment in top_comments:
            retval += ('1. [Comment](%s) in %s by [%s](/user/%s) (Score: %d)\n'
                       % (comment.permalink, comment.submission.title,
                          str(comment.author), str(comment.author),
                          score(comment)))
        return '%s\n' % retval

    def publish_results(self, subreddit, submitters, commenters, submissions,
                        comments, debug=False):
        def timef(timestamp):
            dtime = datetime.fromtimestamp(timestamp)
            return dtime.strftime('%Y-%m-%d %H:%M PDT')

        title = '%s Submissions from %s to %s' % (
            self.post_prefix, timef(self.min_date), timef(self.max_date))
        body = self.basic_stats()
        body += self.top_submitters(submitters)
        body += self.top_commenters(commenters)
        body += self.top_submissions(submissions)
        body += self.top_comments(comments)
        body += self.post_footer % self.max_date

        if not debug:
            msg = ('You are about to submit to subreddit %s as %s.\n'
                   'Are you sure?? yes/[no]: ' % (subreddit,
                                                  str(self.reddit.user)))
            if raw_input(msg).lower() not in ['y', 'yes']:
                print 'Submission aborted'
                debug = True

        if debug:
            print title
            print body
            return

        attempts = 3
        while attempts > 0:
            try:
                self.reddit.submit(subreddit, title, text=body)
                break
            except HTTPError:
                attempts -= 1
        else:
            print 'Submission failed. Here is your data.'
            print 'Title: %s\n' % title
            print body


def main():
    msg = {
        'site': 'The site to connect to defined in your reddit_api.cfg.',
        'user': ('The user to login as. If not specified the user (if any) '
                 'from the site config will be used, otherwise you will be '
                 'prompted for a username.'),
        'pswd': ('The password to use for login. Can only be used in '
                 'combination with "--user". See help for "--user".'),
        }

    parser = OptionParser(usage='usage: %prog [options] subreddit')
    parser.add_option('-s', '--submitters', type='int', default=3,
                      help='Number of top submitters to display '
                      '[default %default]')
    parser.add_option('-c', '--commenters', type='int', default=3,
                      help='Number of top commenters to display '
                      '[default %default]')
    parser.add_option('-d', '--days', type='int', default=7,
                      help=('Number of previous days to include submissions '
                            'from. Use 0 for unlimited. Default: %default'))
    parser.add_option('-v', '--verbose', action='count', default=0,
                      help='Increase the verbosity by 1')
    parser.add_option('-D', '--debug', action='store_true',
                      help='Enable debugging mode. Does not post stats.')
    parser.add_option('-R', '--submission-reddit',
                      help=('Subreddit to submit to. If not present, '
                            'submits to the subreddit processed'))

    group = OptionGroup(parser, 'Site/Authentication options')
    group.add_option('-S', '--site', help=msg['site'])
    group.add_option('-u', '--user', help=msg['user'])
    group.add_option('-p', '--pswd', help=msg['pswd'])
    parser.add_option_group(group)

    options, args = parser.parse_args()
    if len(args) != 1:
        parser.error('Must provide subreddit')

    if options.submission_reddit:
        submission_reddit = options.submission_reddit
    else:
        submission_reddit = args[0]

    srs = SubRedditStats(options.site, options.verbose)
    srs.login(options.user, options.pswd)

    if not srs.fetch_recent_submissions(args[0], max_duration=options.days):
        print 'No submissions were found.'
        return 1
    srs.process_submitters()
    if options.commenters > 0:
        srs.process_commenters()
    srs.publish_results(submission_reddit, options.submitters,
                        options.commenters, 5, 5, options.debug)


if __name__ == '__main__':
    sys.exit(main())
