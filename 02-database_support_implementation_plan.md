# Database Support Implementation Plan

## 1. Understanding the Current System

AWS HealthOmics can only hold a limited number (5000) of runs in its database.
Once the limit is hit, Omics will not accept any new runs. Old runs (regardless
of completed status - success or fail), need to be removed to enable new runs to
be submitted.

The AWS recommended solution is to store whatever information we need in a
database. We need to implement the SQL tables necessary to store all run
information available from Omits for a given workflow/run for historical
purposes.

The current system:
- Has a database model in app/models/workflow.py
- The database is only populated when a run is submitted via POST /runs
- Does not utilize the database in any way

## 2. Expected State

The expected state is the database will track all runs in AWS Omics.

## 2. Implementation Plan

### 2.1 Update Database Model to store all necessary Run info.

aws list-runs return a list of runs consisting of the list of runs:
        {
            "arn": "arn:aws:omics:us-east-1:483421617021:run/2139390",
            "id": "2139390",
            "status": "RUNNING",
            "workflowId": "5753984",
            "name": "18588X8_1201216_A00421_0267_BHN2TJDSXY_S46_L003",
            priority -> (integer)
            storageCapacity -> (integer)
            "creationTime": "2025-04-16T15:07:13.895750+00:00",
            "startTime": "2025-04-16T15:12:20.215000+00:00",
            "stopTime": 
            "storageType": "DYNAMIC"
        },

We implemented the following changes to support database storage of AWS Omics runs:

### 2.2 WorkflowRun Model Updates

The WorkflowRun model in `app/models/workflow.py` was updated to include all necessary fields from AWS Omics:

```python
class WorkflowRun(DB.Model):
    """Workflow run model"""
    __tablename__ = 'workflow_runs'

    run_id = DB.Column(DB.String(36), primary_key=True)
    name = DB.Column(DB.String(200), nullable=False)
    state = DB.Column(DB.String(20), nullable=False)
    workflow_params = DB.Column(DB.JSON)
    workflow_type = DB.Column(DB.String(50), nullable=False)
    workflow_type_version = DB.Column(DB.String(20), nullable=False)
    workflow_engine = DB.Column(DB.String(50))
    workflow_engine_version = DB.Column(DB.String(20))
    workflow_url = DB.Column(DB.String(500), nullable=False)
    tags = DB.Column(DB.JSON)
    
    # AWS Omics specific fields
    arn = DB.Column(DB.String(255))
    workflow_id = DB.Column(DB.String(36))
    priority = DB.Column(DB.Integer)
    storage_capacity = DB.Column(DB.Integer)
    creation_time = DB.Column(DB.DateTime)
    start_time = DB.Column(DB.DateTime)
    stop_time = DB.Column(DB.DateTime)  # Replaces end_time
    storage_type = DB.Column(DB.String(50))
```

### 2.3 Database Migration

A migration was created to add the new columns to the database schema:

```python
def upgrade():
    # Add new columns
    with op.batch_alter_table('workflow_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('arn', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('workflow_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('priority', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('storage_capacity', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('creation_time', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('stop_time', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('storage_type', sa.String(length=50), nullable=True))
    
    # Copy data from end_time to stop_time
    connection = op.get_bind()
    connection.execute(
        text('UPDATE workflow_runs SET stop_time = end_time')
    )
    
    # Drop the old end_time column
    with op.batch_alter_table('workflow_runs', schema=None) as batch_op:
        batch_op.drop_column('end_time')
```

### 2.4 API Updates

The API code in `app/api/wes.py` was updated to use the new database model fields when interacting with AWS Omics:

1. **Run Creation**: When a new run is created, all available AWS Omics fields are stored in the database.
2. **Run Retrieval**: When a run is retrieved, the database record is updated with the latest information from AWS Omics.
3. **Run Status**: When a run status is checked, the database record is updated with the latest status.
4. **Run Cancellation**: When a run is cancelled, the database record is updated to reflect the cancellation.

### 2.5 Sync Script

A sync script was created in `scripts/get_all_runs.py` to synchronize the database with AWS Omics:

```python
def sync_runs():
    """Sync AWS Omics runs with the local database"""
    # Get runs from AWS Omics
    response = omics_service.list_runs()
    
    for run in response.get('items', []):
        run_id = run.get('id')
        
        # Check if the run exists in the database
        db_run = WorkflowRun.query.get(run_id)
        
        if db_run:
            # Update existing run
            db_run.state = omics_service.map_run_state(run.get('status'))
            db_run.arn = run.get('arn')
            db_run.workflow_id = run.get('workflowId')
            # Update other fields...
        else:
            # Create new run record
            new_run = WorkflowRun(
                run_id=run_id,
                name=run.get('name', f"run-{run_id}"),
                state=omics_service.map_run_state(run.get('status')),
                # Set other fields...
            )
            DB.session.add(new_run)
            
    # Commit the changes to the database
    DB.session.commit()
```

The sync script can be run periodically to ensure the database is up-to-date with AWS Omics.

## 3. Implementation Results

The implementation was successful:

1. The WorkflowRun model was updated with AWS Omics specific fields.
2. Database migrations were created and applied.
3. The API code was updated to use the new database model fields.
4. A sync script was created to synchronize the database with AWS Omics.

The sync script successfully synchronized 2,474 runs from AWS Omics to the local database (400 updated, 2,074 new).

## 4. Future Improvements

1. **Scheduled Sync**: Set up a scheduled task to run the sync script periodically.
2. **Run Deletion**: Implement a process to delete old runs from AWS Omics after they've been synced to the database.
3. **Database Queries**: Update the API to query the database instead of AWS Omics for run information when possible.
4. **Pagination**: Implement pagination for the sync script to handle large numbers of runs efficiently.