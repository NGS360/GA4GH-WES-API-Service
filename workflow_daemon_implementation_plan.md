# Implementation Plan for WES Workflow Submission Daemon

## 1. Overview

We'll implement a daemon that:
- Runs as a separate process from the Flask application
- Receives notifications from the WES API when new workflows are submitted
- Polls the database for workflows in the "QUEUED" state as a fallback mechanism
- Submits these workflows to either SevenBridges/Velsera or AWS HealthOmics
- Periodically polls the service providers to check workflow status
- Updates the workflow status in the database
- Logs errors and continues with the next workflow without retrying failed operations

## 2. Architecture

```mermaid
graph TD
    A[WES API Flask App] -->|Stores workflows| B[Database]
    A -->|Notifies| C[Notification Server]
    C -->|Triggers| D[Workflow Submission Daemon]
    D -->|Polls for queued workflows| B
    D -->|Submits workflows| E[Provider Interface]
    E -->|Submits to| F[SevenBridges/Velsera API]
    E -->|Submits to| G[AWS HealthOmics API]
    D -->|Updates workflow status| B
```

## 3. Component Design

### 3.1 Core Daemon

```mermaid
classDiagram
    class WorkflowDaemon {
        +run()
        -poll_for_workflows()
        -process_workflow_by_id(run_id)
        -process_workflow(workflow)
        -update_workflow_status()
        -handle_error(workflow, error)
    }
    
    class NotificationServer {
        +start()
        +stop()
        -handle_notification(run_id)
    }
    
    class ProviderFactory {
        +get_provider(provider_type, config)
    }
    
    class WorkflowProviderInterface {
        <<interface>>
        +submit_workflow(workflow)
        +get_workflow_status(workflow_id)
        +cancel_workflow(workflow_id)
    }
    
    class SevenBridgesProvider {
        +submit_workflow(workflow)
        +get_workflow_status(workflow_id)
        +cancel_workflow(workflow_id)
    }
    
    class HealthOmicsProvider {
        +submit_workflow(workflow)
        +get_workflow_status(workflow_id)
        +cancel_workflow(workflow_id)
    }
    
    WorkflowDaemon --> NotificationServer
    WorkflowDaemon --> ProviderFactory
    ProviderFactory --> WorkflowProviderInterface
    SevenBridgesProvider ..|> WorkflowProviderInterface
    HealthOmicsProvider ..|> WorkflowProviderInterface
```

### 3.2 Database Interaction

The daemon will use SQLAlchemy to interact with the same database as the Flask application. It will:
- Query for workflows in the "QUEUED" state
- Update workflow status as it changes
- Store provider-specific information (like provider workflow IDs) in the database

### 3.3 Provider Interface

We'll create a common interface for all workflow providers with methods for:
- Submitting workflows
- Checking workflow status
- Canceling workflows

Each provider implementation will handle the specifics of interacting with that provider's API.

### 3.4 Notification Server

We'll implement a simple HTTP server that:
- Listens for notifications from the WES API
- Processes workflows immediately when notified
- Runs in a separate thread within the daemon process

## 4. Implementation Steps

### 4.1 Create Provider Interface and Implementations

1. Define a `WorkflowProviderInterface` abstract base class
2. Implement `SevenBridgesProvider` class
   - Add authentication using environment variables
   - Implement workflow submission
   - Implement status checking
   - Implement workflow cancellation
3. Implement `HealthOmicsProvider` class
   - Add authentication using environment variables
   - Implement workflow submission
   - Implement status checking
   - Implement workflow cancellation
4. Create a `ProviderFactory` to instantiate the appropriate provider

### 4.2 Implement Notification Server

1. Create a `NotificationServer` class
   - Implement a simple HTTP server that listens for POST requests
   - Parse the run_id from the request
   - Call a callback function with the run_id

### 4.3 Implement Core Daemon

1. Create a `WorkflowDaemon` class
   - Implement notification server integration
   - Implement polling for queued workflows (as a fallback)
   - Implement workflow processing logic
   - Implement status update logic
   - Implement error handling
2. Create a main script to run the daemon
   - Parse command-line arguments
   - Configure logging
   - Initialize the daemon
   - Start the daemon process

### 4.4 Update WES API

1. Add a function to notify the daemon when a new workflow is submitted
2. Call this function after creating a new workflow in the database

### 4.5 Database Schema Updates

1. Add fields to the `WorkflowRun` model:
   - `provider_type`: The type of provider to use (e.g., "sevenbridges", "healthomics")
   - `provider_id`: The ID of the workflow in the provider's system
   - `provider_status`: The status of the workflow in the provider's system
   - `provider_metadata`: Additional provider-specific metadata

### 4.6 Configuration

1. Define environment variables for authentication:
   - `SEVENBRIDGES_API_TOKEN`: API token for SevenBridges/Velsera
   - `SEVENBRIDGES_API_ENDPOINT`: API endpoint URL for SevenBridges/Velsera
   - `AWS_ACCESS_KEY_ID`: AWS access key for HealthOmics
   - `AWS_SECRET_ACCESS_KEY`: AWS secret key for HealthOmics
   - `AWS_REGION`: AWS region for HealthOmics
2. Define daemon configuration:
   - `DAEMON_POLL_INTERVAL`: How often to poll for new workflows (in seconds)
   - `DAEMON_STATUS_CHECK_INTERVAL`: How often to check workflow status (in seconds)
   - `DAEMON_MAX_CONCURRENT_WORKFLOWS`: Maximum number of workflows to process concurrently
3. Define notification server configuration:
   - `DAEMON_NOTIFICATION_HOST`: Host for the notification server
   - `DAEMON_NOTIFICATION_PORT`: Port for the notification server

## 5. File Structure

```
scripts/
  workflow_daemon.py         # Main daemon script
  test_notification.py       # Test script for notification API
  
app/
  daemon/
    __init__.py
    README.md                # Documentation
    .env.example             # Example environment variables
    workflow_daemon.py       # Core daemon implementation
    notification_server.py   # Notification server implementation
    providers/
      __init__.py
      provider_interface.py  # Abstract base class
      sevenbridges.py        # SevenBridges/Velsera implementation
      healthomics.py         # AWS HealthOmics implementation
      provider_factory.py    # Factory for creating providers
```

## 6. Detailed Implementation

### 6.1 Provider Interface

```python
# app/daemon/providers/provider_interface.py
from abc import ABC, abstractmethod
from app.models.workflow import WorkflowRun

class WorkflowProviderInterface(ABC):
    """Interface for workflow execution providers"""
    
    @abstractmethod
    def submit_workflow(self, workflow: WorkflowRun) -> str:
        """
        Submit a workflow to the provider
        
        Args:
            workflow: The workflow run to submit
            
        Returns:
            str: The provider-specific workflow ID
        """
        pass
    
    @abstractmethod
    def get_workflow_status(self, provider_id: str) -> tuple:
        """
        Get the status of a workflow from the provider
        
        Args:
            provider_id: The provider-specific workflow ID
            
        Returns:
            tuple: (state, outputs, task_logs)
        """
        pass
    
    @abstractmethod
    def cancel_workflow(self, provider_id: str) -> bool:
        """
        Cancel a workflow
        
        Args:
            provider_id: The provider-specific workflow ID
            
        Returns:
            bool: True if cancellation was successful
        """
        pass
```

### 6.2 Notification Server

```python
# app/daemon/notification_server.py
import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Callable

class NotificationHandler(BaseHTTPRequestHandler):
    """HTTP request handler for workflow notifications"""
    
    # This will be set by the NotificationServer
    callback_function = None
    
    def do_POST(self):
        """Handle POST requests"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            run_id = data.get('run_id')
            
            if not run_id:
                self.send_error(400, "Missing run_id in request")
                return
            
            # Call the callback function with the run_id
            if self.callback_function:
                self.callback_function(run_id)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'success'}).encode('utf-8'))
            else:
                self.send_error(500, "Callback function not set")
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
        except Exception as e:
            self.send_error(500, str(e))

class NotificationServer:
    """Server to receive workflow notifications"""
    
    def __init__(self, host='localhost', port=5001, callback=None):
        """
        Initialize the notification server
        
        Args:
            host: The host to bind to
            port: The port to listen on
            callback: Function to call when a notification is received
        """
        self.host = host
        self.port = port
        self.server = None
        self.thread = None
        
        # Set the callback function
        NotificationHandler.callback_function = callback
    
    def start(self):
        """Start the notification server in a separate thread"""
        self.server = HTTPServer((self.host, self.port), NotificationHandler)
        
        # Start the server in a separate thread
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()
    
    def stop(self):
        """Stop the notification server"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join()
```

### 6.3 WES API Notification

```python
# app/api/wes.py (excerpt)
def notify_daemon(run_id):
    """
    Notify the daemon about a new workflow
    
    Args:
        run_id: The ID of the workflow to process
    """
    host = os.environ.get('DAEMON_NOTIFICATION_HOST', 'localhost')
    port = os.environ.get('DAEMON_NOTIFICATION_PORT', '5001')
    
    url = f"http://{host}:{port}"
    payload = {"run_id": run_id}
    
    try:
        requests.post(url, json=payload, timeout=2)
    except requests.RequestException as e:
        current_app.logger.warning(f"Error notifying daemon: {e}")
        # Continue even if notification fails - the daemon will pick up the workflow during polling

# In the workflow submission endpoint
@api.route('/runs')
class WorkflowRuns(Resource):
    @api.doc('run_workflow')
    @api.expect(run_request)
    def post(self):
        """Run a workflow"""
        run_id = str(uuid.uuid4())
        new_run = WorkflowRunModel(
            run_id=run_id,
            state='QUEUED',
            # ... other fields ...
        )
        DB.session.add(new_run)
        DB.session.commit()
        
        # Notify the daemon about the new workflow
        try:
            notify_daemon(run_id)
        except Exception as e:
            current_app.logger.error(f"Error notifying daemon: {e}")
            # Continue even if notification fails
        
        return {'run_id': run_id}
```

## 7. Deployment and Operation

### 7.1 Environment Setup

1. Set up environment variables:
   ```
   # Database
   DATABASE_URI=postgresql://user:password@localhost/wes
   
   # Notification Server
   DAEMON_NOTIFICATION_HOST=localhost
   DAEMON_NOTIFICATION_PORT=5001
   
   # SevenBridges/Velsera
   SEVENBRIDGES_API_TOKEN=your-token
   SEVENBRIDGES_API_ENDPOINT=https://api.sbgenomics.com/v2
   SEVENBRIDGES_PROJECT=your-project-id
   
   # AWS HealthOmics
   AWS_ACCESS_KEY_ID=your-access-key
   AWS_SECRET_ACCESS_KEY=your-secret-key
   AWS_REGION=us-east-1
   
   # Daemon Configuration
   DAEMON_POLL_INTERVAL=300
   DAEMON_STATUS_CHECK_INTERVAL=300
   DAEMON_MAX_CONCURRENT_WORKFLOWS=10
   ```

### 7.2 Running the Daemon

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Run the daemon:
   ```
   python scripts/workflow_daemon.py
   ```

3. For production, use a process manager like Supervisor or systemd to ensure the daemon stays running.

### 7.3 Monitoring and Logging

1. The daemon logs to stdout/stderr, which can be captured by the process manager
2. Consider adding metrics collection for:
   - Number of workflows processed
   - Success/failure rates
   - Processing time

## 8. Testing Strategy

1. Unit tests for each provider implementation
2. Integration tests with mock API responses
3. End-to-end tests with real API calls (using test accounts)
4. Test cases for error handling and recovery
5. Test the notification API using the provided test script

## 9. Future Enhancements

1. Support for additional providers (Arvados)
2. Improved error handling and retry mechanisms
3. Performance optimizations for handling large numbers of workflows
4. Support for workflow versioning and provenance tracking
5. Enhanced notification system with authentication and encryption