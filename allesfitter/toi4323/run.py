#!/usr/bin/env python
import allesfitter

fig = allesfitter.show_initial_guess('.')
#allesfitter.prepare_ttv_fit('.')

allesfitter.ns_fit('.')
allesfitter.ns_output('.')
