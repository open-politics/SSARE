-- Create the necessary tables
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    task_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks (id)
);

-- Insert some initial data
INSERT INTO tasks (name, description) VALUES ('Task 1', 'This is the first task');