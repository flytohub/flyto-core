# flyto-core - 707 files

## [api] (7 files)
  - src/core/api/__init__.py: API endpoint:   init  
  - src/core/api/plugins/__init__.py: API endpoint:   init  
  - src/core/api/plugins/routes.py: API endpoint: route definitions
  - src/core/api/plugins/service.py: API endpoint: PluginCatalogItem, PluginServiceConfig, PluginService
  - src/core/modules/atomic/api/__init__.py: API endpoint:   init  
  - src/core/modules/atomic/api/http_get.py: API endpoint: api_http_get
  - src/core/modules/composite/developer/api_to_notification.py: API endpoint: notifications

## [cli] (15 files)
  - plugins/flyto-official_browser/steps/click.py: Execute_click
  - src/cli/__init__.py:   init  
  - src/cli/config.py: Cli_version, cli_line_width, supported_languages
  - src/cli/i18n.py: Internationalization
  - src/cli/interactive.py: Menuaction, menuitem, colors
  - src/cli/main.py: Main entry
  - src/cli/modules.py: Get_modules_list, format_table, run_modules_command
  - src/cli/params.py: Auto_convert_type, merge_params
  - src/cli/runner.py: Run_workflow
  - src/cli/ui.py: Clear_screen, print_logo, select_language
  - src/cli/workflow.py: Load_config, list_workflows, select_workflow
  - src/core/modules/atomic/browser/click.py: Browserclickmodule
  - src/core/modules/integrations/base/client.py: Api client
  - src/core/modules/integrations/oauth/client.py: Api client
  - src/core/modules/third_party/ai/agents/llm_client.py: Api client

## [common] (1 files)
  - src/core/modules/schema/presets/common.py: Url, text, file_path

## [config] (2 files)
  - src/core/modules/registry/rule_config.py: Config: RuleCategory, RuleDefinition, get_mandatory_rules
  - src/core/runtime/config.py: Config: DEFAULT_CONFIG_PATH, ProcessConfig, ConcurrencyConfig

## [constant] (4 files)
  - src/core/constants.py: Timeouts, databasedefaults, flowcontrollimits
  - src/core/modules/atomic/huggingface/constants.py: Flyto_data_dir, installed_models_file, installed_models_path
  - src/core/modules/quality/constants.py: Secret_patterns, sensitive_param_patterns, stability_levels
  - src/core/modules/schema/constants.py: Visibility, fieldgroup, group_order

## [hook] (5 files)
  - src/core/engine/evidence/executor_hooks.py: Hook: EvidenceExecutorHooks, create_evidence_store, create_evidence_hook
  - src/core/engine/hooks/__init__.py: Hook: create_hooks
  - src/core/engine/hooks/base.py: Hook: ExecutorHooks, NullHooks
  - src/core/engine/hooks/implementations.py: Hook: LoggingHooks, MetricsHooks, CompositeHooks
  - src/core/engine/hooks/models.py: Hook: HookAction, HookContext, HookResult

## [model] (9 files)
  - src/core/engine/breakpoints/models.py: Model: BreakpointStatus, ApprovalMode, BreakpointRequest
  - src/core/engine/evidence/models.py: Model: StepEvidence, BrowserContextProtocol
  - src/core/engine/lineage/models.py: Model: StepCategory, ArtifactType, Artifact
  - src/core/engine/replay/models.py: Model: ReplayMode, ReplayConfig, ReplayResult
  - src/core/engine/sdk/models.py: Model: IntrospectionMode, VarSource, VarAvailability
  - src/core/modules/connection_rules/models.py: Model: ConnectionCategory, ConnectionRule
  - src/core/modules/integrations/base/models.py: Model: IntegrationConfig, APIResponse
  - src/core/modules/integrations/oauth/models.py: Model: OAuthConfig, OAuthToken
  - src/core/testing/runner/models.py: Model: TestStatus, TestCase, TestResult

## [module] (581 files)
  - plugins/flyto-official_browser/main.py: Main entry
  - plugins/flyto-official_browser/steps/__init__.py:   init  
  - plugins/flyto-official_browser/steps/goto.py: Blocked_hosts, blocked_prefixes, execute_goto
  - plugins/flyto-official_browser/steps/screenshot.py: Execute_screenshot
  - plugins/flyto-official_database/main.py: Main entry
  - plugins/flyto-official_database/steps/__init__.py:   init  
  - plugins/flyto-official_database/steps/delete.py: Execute_delete
  - plugins/flyto-official_database/steps/insert.py: Execute_insert
  - plugins/flyto-official_database/steps/query.py: Execute_query
  - plugins/flyto-official_database/steps/update.py: Execute_update
  - plugins/flyto-official_llm/main.py: Main entry
  - plugins/flyto-official_llm/steps/__init__.py:   init  
  - plugins/flyto-official_llm/steps/chat.py: Default_models, execute_chat
  - plugins/flyto-official_llm/steps/embedding.py: Default_models, execute_embedding
  - run.py: Run
  - setup.py: Setup
  - src/core/__init__.py:   init  
  - src/core/analysis/__init__.py:   init  
  - src/core/analysis/html_analyzer.py: Analysis
  - src/core/browser/__init__.py:   init  
  ... and 561 more

## [script] (14 files)
  - scripts/analyze_module_returns.py: Returnpattern, moduleanalysis, returnpatternvisitor
  - scripts/batch_update_connection_rules.py: Base_dir, extract_category, extract_module_id
  - scripts/export_i18n_baseline.py: Internationalization
  - scripts/fix_all_connection_rules.py: Category_rules, get_category, add_can_receive_from
  - scripts/fix_credential_keys.py: Credential_mapping, get_credential_keys, add_credential_keys_to_file
  - scripts/fix_lint_warnings.py: Project_root, modules_path, fix_validate_params_type_hint
  - scripts/fix_missing_can_receive_from.py: Category_rules, get_category, has_can_receive_from
  - scripts/fix_output_descriptions.py: Field_descriptions, fix_output_schema_in_file, main
  - scripts/fix_remaining_warnings.py: Main entry
  - scripts/lint_modules.py: Project_root, compute_violation_fingerprint, load_baseline
  - scripts/migrate_module.py: Moduleinfo, modulemigrator, main
  - scripts/publish_core.py: Get_project_root, get_version, bump_version
  - scripts/validate_all_modules.py: Project_root, run_mypy_check, load_all_modules
  - scripts/validate_schemas.py: Project_root, load_all_modules, validate_schemas

## [service] (1 files)
  - src/core/modules/third_party/ai/services.py: Service: anthropic_chat, google_gemini_chat

## [store] (3 files)
  - src/core/engine/breakpoints/store.py: Store: BreakpointNotifier, NullNotifier, BreakpointStore
  - src/core/engine/evidence/store.py: Store: EvidenceStore
  - src/core/modules/atomic/vector/knowledge_store.py: Store: KnowledgeStore

## [test] (53 files)
  - src/core/modules/atomic/regex/test.py: Test: regex_test
  - src/core/modules/composite/test/__init__.py: Test:   init  
  - src/core/modules/composite/test/api_test.py: Test: ApiTestSuite
  - src/core/modules/composite/test/e2e_flow.py: Test: E2EFlowTest
  - src/core/modules/composite/test/quality_gate.py: Test: QualityGate
  - src/core/modules/composite/test/ui_review.py: Test: UIReview
  - src/core/modules/composite/test/verify_fix.py: Test: VerifyFix
  - src/core/tests/__init__.py: Test:   init  
  - src/core/tests/engine/__init__.py: Test:   init  
  - src/core/tests/engine/test_agent_prompt.py: Test: create_context_with_input, create_context_with_node_output, TestStringifyValue
  - src/core/tests/engine/test_autocomplete.py: Test: create_test_workflow, create_test_catalog, TestAutocompleteEngine
  - src/core/tests/engine/test_context_layers.py: Test: TestLayeredContext, TestContextBuilder, TestCreateContext
  - src/core/tests/engine/test_introspection.py: Test: create_simple_workflow, create_branching_workflow, TestCatalogBuilder
  - src/core/tests/engine/test_item_execution.py: Test: test_items_continue_uses_step_on_error, test_items_from_context_support_non_dict_values
  - src/core/tests/engine/test_resolver.py: Test: TestExpressionParser, TestVariableResolver, TestConditionEvaluation
  - src/core/tests/engine/test_trace_status.py: Test: test_execution_trace_status_legacy_mapping, test_step_trace_status_legacy_mapping, test_item_trace_status_legacy_mapping
  - tests/conftest.py: Test: event_loop, setup_test_env, base_context
  - tests/core/api/__init__.py: Test:   init  
  - tests/core/api/test_plugins.py: Test: TestPluginsInstalledReturnsModuleItemShape, TestPluginModulesAppearInAddNodeMenu, TestPluginModulesCanBeAddedToWorkflow
  - tests/core/runtime/__init__.py: Test:   init  
  ... and 33 more

## [type] (11 files)
  - src/core/modules/quality/types.py: Severity, strictlevel, rulestage
  - src/core/modules/registry/validation_types.py: Validationmode, severity, validationissue
  - src/core/modules/types/__init__.py:   init  
  - src/core/modules/types/context.py: Is_context_compatible, get_context_error_message
  - src/core/modules/types/data_types.py: Is_data_type_compatible
  - src/core/modules/types/enums.py: Executionenvironment, modulelevel, uivisibility
  - src/core/modules/types/environment.py: Get_module_environment, is_module_allowed_in_environment
  - src/core/modules/types/ports.py: Get_default_ports
  - src/core/modules/types/stability.py: Flyto_env_var, default_env, get_current_env
  - src/core/modules/types/visibility.py: Get_default_visibility
  - src/core/runtime/types.py: Invokestatus, invokemetrics, invokeerror

## [util] (1 files)
  - src/core/utils.py: Utility: get_api_key, validate_api_key, validate_required_param
