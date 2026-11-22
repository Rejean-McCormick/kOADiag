# -*- coding: utf-8 -*-
"""Entry point for the kOA ecosystem relationship diagnostic."""
import sys
from koa_ecosystem_diag.cli import main
if __name__=='__main__':
    try:sys.exit(main())
    except Exception as err:
        print('DIAGNOSTIC_ERROR='+type(err).__name__+': '+str(err),file=sys.stderr,flush=True)
        sys.exit(30)
