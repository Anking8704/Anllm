"""Executable entry point with recoverable startup diagnostics."""
from pathlib import Path
import sys,traceback
from runtime_paths import ROOT

runtime_log=(ROOT/'logs'/'runtime.log').open('a',encoding='utf-8',buffering=1)
if sys.stdout is None:sys.stdout=runtime_log
if sys.stderr is None:sys.stderr=runtime_log

try:
    import main
    if '--version' in sys.argv:
        from app_version import APP_VERSION
        runtime_log.write('Anllm '+APP_VERSION+'\n')
        print('Anllm '+APP_VERSION)
    elif '--verify-package' in sys.argv:
        from diagnostics import verify_package
        verify_package()
    elif '--verify-tasks' in sys.argv:
        import check_tasks
    elif '--verify-multitask' in sys.argv:
        import check_multitask
    elif '--verify-reasoning' in sys.argv:
        import check_reasoning
    elif '--verify-requests' in sys.argv:
        import check_requests
    elif '--verify-images' in sys.argv:
        import check_image_limits
    elif '--verify-tray' in sys.argv:
        import check_tray
    elif '--verify-window-style' in sys.argv:
        import check_window_style
    elif '--verify-desktop' in sys.argv:
        import check_desktop
    elif '--verify-stop-shortcut' in sys.argv:
        import check_stop_shortcut
    elif '--desktop-fixture' in sys.argv:
        from desktop_fixture import run
        sys.exit(run())
    else:
        sys.exit(main.main())
except Exception:
    text=traceback.format_exc()
    try:
        import core
        text=core.scrub(text)
    except Exception:pass
    (ROOT/'logs'/'desktop-error.log').write_text(text,encoding='utf-8')
    sys.stderr.write(text)
    sys.exit(1)
