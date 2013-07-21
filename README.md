Plex Media Server Reporter
==========================

This will be an essential logging and reporting system for
[Plex Media Server][0], getting around plex's log size limitation by running a
script periodically that appends new events to our own logs. Soon to be
implemented flexible reporting system will allow you to lock who, what & when
videos are watched.

## Features :

- A fast log saving mechanism, to keep plex logs around for a long as needed
- Gzip compression on logs to reduce their size. Log size 25mb/day vs 600kb/day.
- A somewhat fast log analysis engine, uses minimal ram.
- Soon to be implemented flexible reporting system, report who, what & when
  videos are watched.
  - Get an alert if someone is watching something they're not supposed to be
    watching (ie: children).
  - Possibly setup reporting events to automatically stop video playback.
  - Get logs via email.

## Todo :

- [x] saving logs via script
- [x] move plex.py into a module structure, separate code.
- [ ] start fleshing out the flexible reporting system
- [ ] deal with saving events, deciding when we no longer need to scan older
      logs.
- [ ] events triggering reporting events, retriggering a reporting event if the
      event updates.
- [ ] clean up code
- [ ] now clean up it again, you missed a spot.
- [ ] Lots to be done, log saving code is mostly stable
- [ ] sort out client identification

## Licence :

The code is available at github [https://github.com/kloptops/plex-reporter][1]
under MIT licence : [http://kloptops.mit-license.org][2]

## Objectives :

Now that things are starting to be fleshed out more, I've started to think about
how events/clients will interact. events will be matched to Clients, clients may
actually be multiple devices, or multiple methods of watching media.

For example:
  On an iPod you can watch via the Plex iOS app or the plex website. However
  both are the same device. Or for example, our daughter has, an ipod and a
  laptop. So iOS app, mobile plex website, laptop browser website, and Plex
  Media Center program are just some of the ways that will be linked to her
  single client.

Clients can have certain restrictions applied. TimeRestriction and
RatingRestrictions are just two of the restrictions i've thought of initially,
the possibilies should be endless though. Maybe restrict a certain number of
shows watched per month.

If a restriction is matched, an action will be triggered. Actions can be
restriction specific, or just global. It's possible that if a content rating
restriction is matched, to stop the video immediately (via the
[HTTP_API control][3]). The event code should be fast enough that plex-reporter
and plex-log-saver will be merged into an event daemon.

## Musings :

The event daemon will not query the server about what media is. Immediately
events should be able to be triggered. However if this is too slow, a queue will
be setup. Our simplistic lockfile system is getting old though, perhaps storing
stuff into a SQL database will help?

## Notes :

Possibility of using [http://wiki.plexapp.com/index.php/HTTP_API/Control][3] with
event detection to stop playback of videos not authorized by clients.

When testing on windows, do chcp 65001 in cmd.exe if you get character errors.

 [0]: http://www.plexapp.com/
 [1]: https://github.com/kloptops/plex-reporter
 [2]: http://kloptops.mit-license.org
 [3]: http://wiki.plexapp.com/index.php/HTTP_API/Control
