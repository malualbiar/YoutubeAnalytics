"""
YT Quid Desktop Server Launcher
Embedded WSGI server running Django via Waitress for the Electron desktop application.
"""

import os
import sys
import socket
import argparse
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger('YTQuidDesktop')

def get_free_port(preferred_port=8000):
    """
    Check if the preferred port is available, or find an open dynamic port.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', preferred_port))
            return preferred_port
        except OSError:
            # Preferred port is taken, find any open port
            s.bind(('127.0.0.1', 0))
            return s.getsockname()[1]

def main():
    parser = argparse.ArgumentParser(description="YT Quid Desktop Server")
    parser.add_argument('--port', type=int, default=None, help="Port to bind server on")
    parser.add_argument('--test', action='store_true', help="Run startup self-check and exit")
    args = parser.parse_args()

    # Configure Django environment
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
    
    try:
        import django
        django.setup()
        from django.core.management import call_command
        from core.wsgi import application
        import waitress
    except Exception as e:
        logger.error(f"Failed to initialize Django environment: {e}")
        sys.exit(1)

    # 1. Run automatic database migrations
    try:
        logger.info("Applying database migrations...")
        call_command('migrate', interactive=False, verbosity=0)
        logger.info("Database schema is up to date.")
        
        from apps.authentication.models import User
        if not User.objects.exists():
            logger.info("First run detected. Seeding initial demo data...")
            call_command('seed_demo_data', verbosity=0)
            logger.info("Demo data successfully initialized.")
    except Exception as e:
        logger.warning(f"Database migration/seed notice: {e}")

    # 2. If running test mode, exit cleanly
    if args.test:
        print("SELF_CHECK_OK")
        sys.stdout.flush()
        sys.exit(0)

    # 3. Determine port
    port = args.port if args.port else get_free_port(8000)
    server_url = f"http://127.0.0.1:{port}"

    # 4. Notify Electron that the server is ready
    print(f"SERVER_PORT:{port}")
    print(f"SERVER_READY:{server_url}")
    sys.stdout.flush()

    logger.info(f"YT Quid desktop backend serving at {server_url}")

    # 5. Start Waitress production WSGI server with static file handling
    from django.contrib.staticfiles.handlers import StaticFilesHandler
    wsgi_app = StaticFilesHandler(application)

    try:
        waitress.serve(
            wsgi_app,
            host='127.0.0.1',
            port=port,
            threads=6,
            _quiet=True
        )
    except KeyboardInterrupt:
        logger.info("Server terminated by user/parent process.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
