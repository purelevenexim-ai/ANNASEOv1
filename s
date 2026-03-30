                                  Table "public.strategy_jobs"
     Column     |           Type           | Collation | Nullable |           Default            
----------------+--------------------------+-----------+----------+------------------------------
 id             | character varying(36)    |           | not null | 
 project_id     | character varying(36)    |           |          | 
 status         | character varying(32)    |           | not null | 'pending'::character varying
 progress       | integer                  |           | not null | 0
 current_step   | character varying        |           |          | 
 input_payload  | json                     |           |          | 
 result_payload | json                     |           |          | 
 error_message  | text                     |           |          | 
 created_at     | timestamp with time zone |           |          | now()
 started_at     | timestamp with time zone |           |          | 
 completed_at   | timestamp with time zone |           |          | 
 retry_count    | integer                  |           | not null | 0
Indexes:
    "strategy_jobs_pkey" PRIMARY KEY, btree (id)
    "ix_strategy_jobs_project" btree (project_id)
    "ix_strategy_jobs_status" btree (status)

