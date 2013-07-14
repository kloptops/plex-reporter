Plex Media Server Reporter
==========================

This will be an essential logging and reporting system for
[Plex Media Server][0], getting around plex's log size limitation by running a
script periodically that appends new events to our own logs.

## Features :

- A fast log saving mechanism, to keep plex logs around for a long as needed
- Gzip compression on logs to reduce their size. Log size 25mb/day vs 600kb/day.
- More to come!

## Todo :

- [x] saving logs via script
- [x] move plex.py into a module structure, separate code.
- [ ] Lots to be done, log saving code is mostly stable

## Licence :

The code is available at github [https://github.com/kloptops/plex-reporter][1]
under MIT licence : [http://kloptops.mit-license.org][2]

 [0]: http://www.plexapp.com/
 [1]: https://github.com/kloptops/plex-reporter
 [2]: http://kloptops.mit-license.org

## Note :

When testing on windows, do chcp 65001 in cmd.exe if you get character errors.
