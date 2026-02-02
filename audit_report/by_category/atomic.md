# Category: atomic

Total Modules: 31
Modules with Issues: 31

## Modules

### api.http_get

Issues: 4 (Critical: 0, Warning: 4, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| url | missing_description | warning | URL to navigate or request |
| headers | missing_description | warning | HTTP headers |
| query | missing_description | warning | Query string or parameters |
| timeout | missing_description | warning | Maximum time to wait in milliseconds |

### array.filter

Issues: 1 (Critical: 0, Warning: 1, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| condition | missing_placeholder | warning | value > 0 |

### array.sort

Issues: 3 (Critical: 0, Warning: 1, Info: 2)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| order | missing_placeholder | warning | Enter text... |
| input_types | missing_input_types | info | ['any'] |
| output_types | missing_output_types | info | ['any'] |

### array.unique

Issues: 2 (Critical: 0, Warning: 0, Info: 2)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| input_types | missing_input_types | info | ['any'] |
| output_types | missing_output_types | info | ['any'] |

### file.exists

Issues: 2 (Critical: 0, Warning: 0, Info: 2)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| input_types | missing_input_types | info | ['any'] |
| output_types | missing_output_types | info | ['any'] |

### file.read

Issues: 1 (Critical: 0, Warning: 1, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| encoding | missing_placeholder | warning | utf-8 |

### file.write

Issues: 4 (Critical: 0, Warning: 2, Info: 2)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| encoding | missing_placeholder | warning | utf-8 |
| mode | missing_placeholder | warning | Enter text... |
| input_types | missing_input_types | info | ['any'] |
| output_types | missing_output_types | info | ['any'] |

### http.request

Issues: 8 (Critical: 0, Warning: 8, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| method | missing_placeholder | warning | Enter text... |
| headers | missing_description | warning | HTTP headers |
| body | missing_description | warning | Request body |
| query | missing_description | warning | Query string or parameters |
| content_type | missing_placeholder | warning | Enter text... |
| auth | missing_description | warning | Key-value data structure |
| timeout | missing_description | warning | Maximum time to wait in milliseconds |
| response_type | missing_placeholder | warning | Enter text... |

### http.response_assert

Issues: 1 (Critical: 0, Warning: 1, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| content_type | missing_placeholder | warning | Enter text... |

### llm.chat

Issues: 6 (Critical: 0, Warning: 6, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| prompt | missing_description | warning | Text input |
| system_prompt | missing_description | warning | Text input |
| provider | missing_placeholder | warning | Enter text... |
| model | missing_placeholder | warning | Enter text... |
| response_format | missing_placeholder | warning | Enter text... |
| api_key | missing_placeholder | warning | Enter text... |

### llm.code_fix

Issues: 3 (Critical: 0, Warning: 3, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| fix_mode | missing_placeholder | warning | Enter text... |
| model | missing_placeholder | warning | Enter text... |
| api_key | missing_placeholder | warning | Enter text... |

### math.calculate

Issues: 2 (Critical: 0, Warning: 2, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| operation | missing_description | warning | Operation type |
| operation | missing_placeholder | warning | Enter text... |

### port.check

Issues: 1 (Critical: 0, Warning: 1, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| host | missing_placeholder | warning | Enter text... |

### port.wait

Issues: 1 (Critical: 0, Warning: 1, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| host | missing_placeholder | warning | Enter text... |

### process.list

Issues: 4 (Critical: 0, Warning: 3, Info: 1)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| filter_name | missing_description | warning | Text input |
| filter_name | missing_placeholder | warning | Enter text... |
| include_status | missing_description | warning | True or false toggle |
| input_types | missing_input_types | info | ['any'] |

### process.start

Issues: 9 (Critical: 0, Warning: 9, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| command | missing_description | warning | Command to run |
| cwd | missing_description | warning | Working directory |
| env | missing_description | warning | Environment variables |
| name | missing_description | warning | Name identifier |
| wait_timeout | missing_description | warning | Numeric value |
| capture_output | missing_description | warning | True or false toggle |
| log_file | missing_description | warning | Text input |
| log_file | missing_placeholder | warning | Enter text... |
| auto_restart | missing_description | warning | True or false toggle |

### process.stop

Issues: 9 (Critical: 0, Warning: 9, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| process_id | missing_description | warning | Text input |
| process_id | missing_placeholder | warning | Enter text... |
| name | missing_description | warning | Name identifier |
| pid | missing_description | warning | Numeric value |
| signal | missing_description | warning | Text input |
| signal | missing_placeholder | warning | Enter text... |
| timeout | missing_description | warning | Maximum time to wait in milliseconds |
| force | missing_description | warning | True or false toggle |
| stop_all | missing_description | warning | True or false toggle |

### shell.exec

Issues: 7 (Critical: 0, Warning: 7, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| command | missing_description | warning | Command to run |
| cwd | missing_description | warning | Working directory |
| env | missing_description | warning | Environment variables |
| timeout | missing_description | warning | Maximum time to wait in milliseconds |
| capture_stderr | missing_description | warning | True or false toggle |
| encoding | missing_placeholder | warning | utf-8 |
| raise_on_error | missing_description | warning | True or false toggle |

### testing.e2e.run_steps

Issues: 2 (Critical: 0, Warning: 2, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| stop_on_failure | missing_description | warning | True or false toggle |
| timeout_per_step | missing_description | warning | Numeric value |

### testing.gate.evaluate

Issues: 1 (Critical: 0, Warning: 1, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| fail_on_breach | missing_description | warning | True or false toggle |

### testing.http.run_suite

Issues: 2 (Critical: 0, Warning: 2, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| base_url | missing_description | warning | Text input |
| headers | missing_description | warning | HTTP headers |

### testing.lint.run

Issues: 3 (Critical: 0, Warning: 3, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| linter | missing_description | warning | Text input |
| linter | missing_placeholder | warning | Enter text... |
| fix | missing_description | warning | True or false toggle |

### testing.report.generate

Issues: 5 (Critical: 0, Warning: 5, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| results | missing_description | warning | Key-value data structure |
| format | missing_description | warning | Output format |
| format | missing_placeholder | warning | json |
| title | missing_description | warning | Title text |
| title | missing_placeholder | warning | Enter title... |

### testing.scenario.run

Issues: 1 (Critical: 0, Warning: 1, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| context | missing_description | warning | Key-value data structure |

### testing.security.scan

Issues: 4 (Critical: 0, Warning: 4, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| scan_type | missing_description | warning | Text input |
| scan_type | missing_placeholder | warning | Enter text... |
| severity_threshold | missing_description | warning | Text input |
| severity_threshold | missing_placeholder | warning | Enter text... |

### testing.suite.run

Issues: 1 (Critical: 0, Warning: 1, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| parallel | missing_description | warning | True or false toggle |

### testing.unit.run

Issues: 3 (Critical: 0, Warning: 3, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| pattern | missing_description | warning | Pattern to match |
| pattern | missing_placeholder | warning | \d+ |
| verbose | missing_description | warning | True or false toggle |

### testing.visual.compare

Issues: 3 (Critical: 0, Warning: 3, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| actual | missing_placeholder | warning | Enter text... |
| expected | missing_placeholder | warning | Enter text... |
| output_diff | missing_description | warning | True or false toggle |

### ui.evaluate

Issues: 2 (Critical: 0, Warning: 2, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| app_type | missing_placeholder | warning | Enter text... |
| api_key | missing_placeholder | warning | Enter text... |

### vision.analyze

Issues: 7 (Critical: 0, Warning: 7, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| analysis_type | missing_placeholder | warning | Enter text... |
| output_format | missing_placeholder | warning | Enter text... |
| model | missing_placeholder | warning | Enter text... |
| api_key | missing_description | warning | Text input |
| header_name | missing_description | warning | Text input |
| header_name | missing_placeholder | warning | Enter text... |
| detail | missing_placeholder | warning | Enter text... |

### vision.compare

Issues: 5 (Critical: 0, Warning: 5, Info: 0)

| Field | Issue | Level | Suggestion |
|-------|-------|-------|------------|
| comparison_type | missing_placeholder | warning | Enter text... |
| model | missing_placeholder | warning | Enter text... |
| api_key | missing_description | warning | Text input |
| header_name | missing_description | warning | Text input |
| header_name | missing_placeholder | warning | Enter text... |
