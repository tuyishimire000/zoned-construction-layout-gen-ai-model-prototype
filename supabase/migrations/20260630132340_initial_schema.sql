CREATE TABLE chat_sessions (
	id VARCHAR NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	current_state JSON, 
	PRIMARY KEY (id)
);

CREATE TABLE chat_messages (
	id VARCHAR NOT NULL, 
	session_id VARCHAR, 
	role VARCHAR NOT NULL, 
	content TEXT NOT NULL, 
	timestamp TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES chat_sessions (id)
);

