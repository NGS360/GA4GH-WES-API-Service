#!/usr/bin/env python3
"""
Main script to run the workflow submission daemon
"""
import os
import sys
import time
import logging
import argparse
import signal
from dotenv import load_dotenv

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.daemon.workflow_daemon import WorkflowDaemon


def setup_logging(log_level, log_file=None):
    """
    Set up logging configuration
    
    Args:
        log_level: The logging level
        log_file: Optional file to log to
    """
    handlers = [logging.StreamHandler()]
    
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
        handlers=handlers
    )


def signal_handler(signum, frame):
    """
    Handle signals to gracefully shut down the daemon
    
    Args:
        signum: The signal number
        frame: The current stack frame
    """
    logging.info(f"Received signal {signum}, shutting down")
    if daemon:
        daemon.stop()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='WES Workflow Submission Daemon')
    parser.add_argument('--log-level', default='INFO', 
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='Set the logging level')
    parser.add_argument('--log-file', help='Log to this file in addition to stdout')
    parser.add_argument('--db-uri', help='Database URI (overrides environment variable)')
    parser.add_argument('--poll-interval', type=int, 
                        help='How often to poll for new workflows (in seconds)')
    parser.add_argument('--status-check-interval', type=int, 
                        help='How often to check workflow status (in seconds)')
    parser.add_argument('--max-concurrent-workflows', type=int, 
                        help='Maximum number of workflows to process concurrently')
    args = parser.parse_args()
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Set up logging
    setup_logging(args.log_level, args.log_file)
    
    # Get database URI
    db_uri = args.db_uri or os.environ.get('DATABASE_URI')
    if not db_uri:
        logging.error("Database URI not provided. Use --db-uri or set DATABASE_URI environment variable.")
        sys.exit(1)
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and run the daemon
    global daemon
    daemon = WorkflowDaemon(db_uri)
    
    # Override configuration from command line if provided
    if args.poll_interval:
        daemon.poll_interval = args.poll_interval
        os.environ['DAEMON_POLL_INTERVAL'] = str(args.poll_interval)
    
    if args.status_check_interval:
        daemon.status_check_interval = args.status_check_interval
        os.environ['DAEMON_STATUS_CHECK_INTERVAL'] = str(args.status_check_interval)
    
    if args.max_concurrent_workflows:
        daemon.max_concurrent_workflows = args.max_concurrent_workflows
        os.environ['DAEMON_MAX_CONCURRENT_WORKFLOWS'] = str(args.max_concurrent_workflows)
    
    # Log available providers
    from app.daemon.providers.provider_factory import ProviderFactory
    providers = ProviderFactory.get_available_providers()
    logging.info(f"Available workflow providers: {', '.join(providers.keys())}")
    
    # Run the daemon
    daemon.run()


if __name__ == '__main__':
    daemon = None
    main()