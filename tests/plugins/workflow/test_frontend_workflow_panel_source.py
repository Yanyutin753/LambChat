from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PANEL_SOURCE = REPO_ROOT / "frontend" / "src" / "plugins" / "workflow" / "WorkflowPanel.tsx"
TAB_CONTENT_SOURCE = REPO_ROOT / "frontend" / "src" / "components" / "layout" / "AppContent" / "TabContent.tsx"
CONTRACT_UTILS_SOURCE = (
    REPO_ROOT / "frontend" / "src" / "plugins" / "workflow" / "contractUtils.ts"
)
PLUGIN_LOCALES_DIR = REPO_ROOT / "plugins" / "system" / "workflow" / "frontend" / "locales"
PLUGIN_DATA_LOCALES_DIR = REPO_ROOT / "plugin-data" / "workflow" / "frontend" / "locales"


def test_workflow_panel_uses_plugin_owned_i18n_resources() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")
    i18n_source = (REPO_ROOT / "frontend" / "src" / "i18n" / "index.ts").read_text(encoding="utf-8")
    plugin_locale_source = (
        REPO_ROOT / "frontend" / "src" / "i18n" / "pluginLocales.ts"
    ).read_text(encoding="utf-8")

    assert 'from "react-i18next"' in source
    assert "useTranslation()" in source
    assert "loadPluginLocaleResources" in i18n_source
    assert "mergeLocaleResource(base, pluginLocaleResources[language] ?? {})" in i18n_source
    assert "../../../plugins/system/*/frontend/locales/*.json" in plugin_locale_source
    assert "../../../plugins/preinstalled/*/frontend/locales/*.json" in plugin_locale_source
    assert "../../../plugin-data/*/frontend/locales/*.json" in plugin_locale_source
    assert "loadSupplementalPluginLocaleResources" in plugin_locale_source
    assert "loadPluginLocaleResources" in plugin_locale_source

    required_locale_keys = [
        ("workflowPlugin", "nav", "label"),
        ("workflowPlugin", "editor", "graph", "title"),
        ("workflowPlugin", "editor", "route", "importTitle"),
        ("workflowPlugin", "editor", "route", "createTitle"),
        ("workflowPlugin", "editor", "create", "createBlank"),
        ("workflowPlugin", "editor", "graph", "inputContract"),
        ("workflowPlugin", "editor", "run", "outputContract"),
        ("workflowPlugin", "editor", "run", "outputContractStatus", "satisfied"),
        ("workflowPlugin", "editor", "run", "workflowInterface"),
        ("workflowPlugin", "editor", "credentials", "title"),
        ("workflowPlugin", "editor", "toast", "invalidWorkflowInput"),
    ]
    for language in ("en", "zh", "ja", "ko", "ru"):
        locale_file = (
            PLUGIN_LOCALES_DIR / f"{language}.json"
            if language == "en"
            else PLUGIN_DATA_LOCALES_DIR / f"{language}.json"
        )
        locale = json.loads(locale_file.read_text(encoding="utf-8"))
        for key_path in required_locale_keys:
            value: object = locale
            for key in key_path:
                assert isinstance(value, dict)
                value = value[key]
            assert isinstance(value, str)


def test_workflow_panel_renders_schema_aware_run_input_form() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")
    contract_source = CONTRACT_UTILS_SOURCE.read_text(encoding="utf-8")

    assert "function WorkflowInputForm" in source
    assert 'from "./contractUtils"' in source
    assert "sampleWorkflowInputFromSchema" in source
    assert "sampleWorkflowInputValue" in source
    assert "workflowInputDraftStatus" in source
    assert "export function missingWorkflowInputFieldsForSchema" in contract_source
    assert "export function workflowInputSchemaError" in contract_source
    assert "schemaPath(path, field)" in contract_source
    assert "`${fieldPath}[${index}]`" in contract_source
    assert "parseRunInputObject" in source
    assert "runInputWithFieldValue" in source
    assert "Array.isArray(field.schema.enum)" in source
    assert 'type="checkbox"' in source
    assert 'type="number"' in source
    assert 'field.type === "array" || field.type === "object"' in source
    assert "field.schema.format === \"email\"" in source
    assert "field.schema.format === \"url\" || field.schema.format === \"uri\"" in source
    assert "runInputDraftStatus.message" in source
    assert "Boolean(runInputDraftStatus.message)" in source
    assert "workflowInputDraftMessage(runInputDraftStatus, t)" in source
    assert 'toast.error(runInputDraftMessage || t("workflowPlugin.editor.toast.invalidWorkflowInput"))' in source
    assert "<WorkflowInputForm" in source


def test_workflow_panel_renders_file_metadata_inputs_without_upload_side_effects() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "inputKind" in source
    assert 'property["x-lambchat-input-kind"]' in source
    assert "function fileMetadataValue" in source
    assert "function fileMetadataListValue" in source
    assert "function runInputWithFileMetadataValue" in source
    assert "function runInputWithFileMetadataListItemValue" in source
    assert "function runInputWithAddedFileMetadataItem" in source
    assert "function runInputWithRemovedFileMetadataItem" in source
    assert "const FILE_METADATA_FIELDS" in source
    assert 'field.inputKind === "file" && field.type === "object"' in source
    assert 'field.inputKind === "file" && field.type === "array"' in source
    assert '["name", "File name"]' in source
    assert '["url", "URL"]' in source
    assert '["mime_type", "MIME type"]' in source
    assert 'type={metadataKey === "url" ? "url" : "text"}' in source
    assert "Add file" in source
    assert "Remove" in source
    assert 'type="file"' not in source


def test_workflow_panel_keeps_json_fallback_after_schema_form() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    form_index = source.index("<WorkflowInputForm")
    json_textarea_index = source.index('value={runInput}', form_index)
    assert form_index < json_textarea_index
    assert "onChange={setRunInput}" in source
    assert "onChange={(event) => setRunInput(event.target.value)}" in source


def test_workflow_panel_creates_blank_workflow_and_opens_editor() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "function buildBlankWorkflowPluginDsl" in source
    assert "function blankWorkflowNameFromDraft" in source
    assert 'const navigate = useNavigate();' in source
    assert "const [searchParams] = useSearchParams();" in source
    assert 'const createMode = searchParams.get("create");' in source
    assert 'createMode === "blank"' in source
    assert "const handleCreateBlankWorkflow = useCallback(async () =>" in source
    assert 'to="/workflows?create=blank"' in source
    assert 'data-testid="workflow-create-blank-submit"' in source
    assert "source_payload: sourcePayload" in source
    assert "dry_run: false" in source
    assert "navigate(workflowEditorPath(response.workflow_id))" in source
    assert 'type: "start"' in source
    assert 'type: "answer"' in source
    assert 'variables: [{ name: "message", type: "string", required: true, description: defaultText.entryMessageDescription }]' in source
    assert "input_schema" in source
    assert "output_schema" in source
    assert 'answer: "{{message}}"' in source
    assert 'edges: [{ id: "start-answer", source: "start", target: "answer" }]' in source
    assert 't("workflowPlugin.editor.toolbar.newWorkflow")' in source


def test_workflow_panel_keeps_workflow_home_list_first() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert 'createMode === "import"' in source
    assert 'createMode === "blank"' in source
    assert 'workflowRouteMode === "create"' in source
    assert 'workflowRouteMode === "import"' in source
    assert 'workflowRouteMode === "editor"' in source
    assert 'workflowRouteMode === "list"' in source
    assert 'workflowRouteMode === "editor" || workflowRouteMode === "run"' in source
    assert 'to="/workflows?create=import"' in source
    assert "shouldShowWorkflowSidebar" not in source
    assert 'lg:grid-cols-[18rem_minmax(0,1fr)]' not in source

    header_list_start = source.index('{workflowRouteMode === "list" && (')
    list_start = source.index('{workflowRouteMode === "list" && (', header_list_start + 1)
    list_end = source.index('{workflowRouteMode === "create" && (', list_start)
    list_source = source[list_start:list_end]
    assert 't("workflowPlugin.editor.inventory.title")' in list_source
    assert 'data-testid="workflow-import-dry-run"' not in list_source
    assert 'data-testid="workflow-run-version"' not in list_source
    assert "<GraphEditor" not in list_source
    assert "<WorkflowInputForm" not in list_source
    assert "<CompatibilityMatrixPanel" not in list_source

    create_start = source.index('{workflowRouteMode === "create" && (', list_end)
    import_start = source.index('{workflowRouteMode === "import" && (', create_start)
    create_source = source[create_start:import_start]
    assert 'data-testid="workflow-create-blank-submit"' in create_source
    assert "<GraphEditor" not in create_source

    import_end = source.index('{workflowRouteMode === "editor" && (', import_start)
    import_source = source[import_start:import_end]
    assert 'data-testid="workflow-import-dry-run"' in import_source
    assert 'data-testid="workflow-import-submit"' in import_source
    assert "<GraphEditor" not in import_source

    editor_start = import_end
    side_panel_start = source.index('{(workflowRouteMode === "editor" || workflowRouteMode === "run") && (', editor_start)
    editor_source = source[editor_start:side_panel_start]
    assert "<GraphEditor" in editor_source

    header_start = source.index('<div className="flex flex-wrap items-center gap-2">')
    header_end = source.index("{loadError && (", header_start)
    header_source = source[header_start:header_end]
    assert 'to={workflowEditorPath(selectedWorkflow.workflow_id)}' not in header_source
    assert 'workflowRouteMode !== "list"' in header_source
    assert 'workflowRouteMode === "list" && (' in header_source
    assert 'workflowRouteMode === "create" && (' in header_source
    assert 'workflowRouteMode === "import" && (' in header_source


def test_workflow_panel_receives_top_level_workflow_tab_mode() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")
    tab_content_source = TAB_CONTENT_SOURCE.read_text(encoding="utf-8")

    assert 'activeTab === "workflows-editor"' in tab_content_source
    assert 'activeTab === "workflows-run"' in tab_content_source
    assert '<WorkflowAwarePanel activeTab={activeTab} />' in tab_content_source
    assert "type WorkflowPanelProps" in source
    assert "export function WorkflowPanel({ activeTab }: WorkflowPanelProps = {})" in source
    assert 'activeTab === "workflows-run"' in source
    assert 'activeTab === "workflows-editor"' in source


def test_workflow_panel_edits_workflow_entry_and_exit_contracts() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "const WORKFLOW_CONTRACT_FIELD_TYPES" in source
    assert "function inputContractFallback" in source
    assert "function outputContractFallback" in source
    assert "function schemaFromContractRows" in source
    assert "function inputContractPatch" in source
    assert "function outputContractPatch" in source
    assert "function answerOutputContractRow" in source
    assert "function answerOutputContractPatch" in source
    assert 'selectedNode.type === "start"' in source
    assert 'selectedNode.type === "answer"' in source
    assert 'selectedNode.type === "end"' in source
    assert 't("workflowPlugin.editor.graph.inputContract")' in source
    assert 't("workflowPlugin.editor.run.outputContract")' in source
    assert 't("workflowPlugin.editor.graph.addInputField")' in source
    assert 't("workflowPlugin.editor.graph.addOutputField")' in source
    assert "variables: rows" in source
    assert "outputs: rows" in source
    assert 'input_schema: schemaFromContractRows(rows, "required")' in source
    assert "output_schema: schemaFromContractRows(rows)" in source
    assert 'name: "answer"' in source
    assert 'outputs: undefined' in source
    assert 'value="answer"' in source
    assert "answerOutputContractPatch({" in source


def test_workflow_graph_marks_entry_and_exit_nodes() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert 'boundaryRole: "entry" | "exit" | null' in source
    assert "function workflowNodeBoundaryRole" in source
    assert 'if (nodeType === "start") return "entry";' in source
    assert 'if (nodeType === "answer" || nodeType === "end") return "exit";' in source
    assert "const boundaryRole = data.boundaryRole;" in source
    assert 't("workflowPlugin.editor.boundaries.roleEntry")' in source
    assert 't("workflowPlugin.editor.boundaries.roleExit")' in source
    assert "nodeId: string;" in source
    assert "nodeId: node.id" in source
    assert 'data-testid={`workflow-canvas-node-${data.nodeId}`}' in source
    assert 'data-testid={`workflow-canvas-target-handle-${data.nodeId}`}' in source
    assert 'data-testid={`workflow-canvas-source-handle-${data.nodeId}-${handle}`}' in source
    assert 'boundaryRole: workflowNodeBoundaryRole(node.type || "answer")' in source


def test_workflow_panel_shows_workflow_boundary_summary() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "type WorkflowBoundarySummaryItem" in source
    assert "function workflowBoundarySummaryItems(graph: EditableGraph, defaultText: WorkflowDefaultText)" in source
    assert 'node.type === "start"' in source
    assert 'node.type === "answer"' in source
    assert 'node.type === "end"' in source
    assert "inputContractRows(node.data || {}, defaultText).filter((field) => contractFieldName(field)).length" in source
    assert "contractFieldName(answerOutputContractRow(node.data || {}, defaultText)) ? 1 : 0" in source
    assert "outputContractRows(node.data || {}, defaultText).filter((field) => contractFieldName(field)).length" in source
    assert "function WorkflowBoundarySummary" in source
    assert 't("workflowPlugin.editor.boundaries.title")' in source
    assert '[t("workflowPlugin.editor.boundaries.entries"), entryItems.length]' in source
    assert '[t("workflowPlugin.editor.boundaries.exits"), exitItems.length]' in source
    assert '[t("workflowPlugin.editor.boundaries.inputFields"), inputFieldCount]' in source
    assert '[t("workflowPlugin.editor.boundaries.outputFields"), outputFieldCount]' in source
    assert 'data-testid="workflow-boundary-summary"' in source
    assert "<WorkflowBoundarySummary graph={graph} onSelectNode={onSelectNode} />" in source
    assert "workflowBoundarySummaryItems(graph, defaultText)" in source


def test_workflow_panel_exposes_document_extractor_node_in_graph_editor() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert '"document_extractor"' in source
    assert 'if (type === "document_extractor")' in source
    assert 'variable_selector: ["attachment"]' in source
    assert 'output_key: "document_text"' in source


def test_workflow_panel_exposes_descriptor_compatible_tool_and_http_defaults() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert 'if (type === "tool_call")' in source
    assert "tool_configurations" in source
    assert 'name: "scope", value: "published"' in source
    assert 'name: "query", value_selector: ["message"]' in source
    assert 'if (type === "http_request")' in source
    assert 'request_method: "GET"' in source
    assert 'endpoint: "https://example.com"' in source
    assert "header_parameters" in source
    assert "query_parameters" in source
    assert "request_body" in source


def test_workflow_panel_exposes_list_operator_presets_in_graph_editor() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "const LIST_OPERATOR_PRESETS" in source
    assert 'id: "sort_desc"' in source
    assert 'operation: "sort"' in source
    assert 'sort_by: "score"' in source
    assert 'direction: "desc"' in source
    assert 'id: "sum_field"' in source
    assert 'operation: "sum"' in source
    assert 'id: "pluck_field"' in source
    assert 'operation: "pluck"' in source
    assert 'value_key: "profile.name"' in source
    assert 'id: "filter_conditions"' in source
    assert 'operation: "filter"' in source
    assert 'id: "find_match"' in source
    assert 'operation: "find"' in source
    assert 'id: "count_matches"' in source
    assert 'operation: "count_matching"' in source
    assert 'conditions: [' in source
    assert 'variable_selector: ["item", "score"]' in source
    assert "addNodeType" in source
    assert "addNodePreset" in source
    assert "onAddNodeTypeChange" in source
    assert "onAddNodePresetChange" in source
    assert 'addNodeType === "list_operator"' in source
    assert "LIST_OPERATOR_PRESETS.map" in source


def test_workflow_panel_resets_node_data_when_editing_node_type() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "function defaultNodeData" in source
    assert "onResetNodeData" in source
    assert "const handleResetNodeData" in source
    assert 't("workflowPlugin.editor.graph.resetNodeData")' in source
    assert "const nextType = event.target.value" in source
    assert "data: defaultNodeData(nextType, nextTitle" in source
    assert "data: defaultNodeData(type, title" in source


def test_workflow_panel_updates_selected_list_operator_from_preset() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert 'selectedNode.type === "list_operator"' in source
    assert "const nextPreset = event.target.value" in source
    assert "onAddNodePresetChange(nextPreset)" in source
    assert 'data: defaultNodeData("list_operator", selectedNode.title || selectedNode.id || defaultText.listOperatorTitle, defaultText, nextPreset)' in source


def test_workflow_panel_exposes_list_operator_field_controls() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "function selectorText" in source
    assert "function selectorFromText" in source
    assert "function dataTextValue" in source
    assert "function listOperatorFieldKey" in source
    assert "const LIST_OPERATOR_CONDITION_OPERATIONS = new Set" in source
    assert "function listOperatorUsesConditions" in source
    assert "const selectedNodeData = selectedNode?.data || {}" in source
    assert "const patchSelectedNodeData = (patch: Record<string, unknown>)" in source
    assert "onUpdateNode(selectedNode.id, { data: { ...selectedNodeData, ...patch } })" in source
    assert 'value={dataTextValue(selectedNodeData, "operation")}' in source
    assert 'patchSelectedNodeData({ operation: event.target.value })' in source
    assert "value={selectorText(selectedNodeData.variable_selector)}" in source
    assert "patchSelectedNodeData({ variable_selector: selectorFromText(event.target.value) })" in source
    assert 'value={dataTextValue(selectedNodeData, "output_key")}' in source
    assert 'selectedNodeData.operation === "sort"' in source
    assert 'patchSelectedNodeData({ direction: event.target.value })' in source
    assert 'selectedNodeData.operation === "sum"' in source
    assert 'selectedNodeData.operation === "pluck"' in source
    assert "value={dataTextValue(selectedNodeData, listOperatorFieldKey(selectedNodeData))}" in source
    assert "patchSelectedNodeData({ [listOperatorFieldKey(selectedNodeData)]: event.target.value })" in source
    assert "listOperatorUsesConditions(selectedNodeData)" in source
    assert 'value={dataTextValue(selectedNodeData, "logical_operator") || "and"}' in source
    assert "patchSelectedNodeData({ logical_operator: event.target.value })" in source
    assert "function listOperatorConditionFallback" in source
    assert "function listOperatorConditionRows" in source
    assert "function listOperatorConditionValue" in source
    assert "function listOperatorConditionsWithValue" in source
    assert "function listOperatorConditionsWithAddedCondition" in source
    assert "function listOperatorConditionsWithoutIndex" in source
    assert "listOperatorConditionRows(selectedNodeData.conditions).map((condition, conditionIndex)" in source
    assert 'conditions: listOperatorConditionsWithAddedCondition(selectedNodeData.conditions)' in source
    assert 'conditions: listOperatorConditionsWithValue(selectedNodeData.conditions, conditionIndex, "variable_selector", selectorFromText(event.target.value))' in source
    assert 'conditions: listOperatorConditionsWithValue(selectedNodeData.conditions, conditionIndex, "operator", event.target.value)' in source
    assert 'conditions: listOperatorConditionsWithValue(selectedNodeData.conditions, conditionIndex, "value", event.target.value)' in source
    assert 'conditions: listOperatorConditionsWithoutIndex(selectedNodeData.conditions, conditionIndex)' in source
    assert "disabled={disabled || listOperatorConditionRows(selectedNodeData.conditions).length <= 1}" in source


def test_workflow_panel_exposes_iteration_and_document_field_controls() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert 'selectedNode.type === "iteration"' in source
    assert "value={selectorText(selectedNodeData.iterator_selector)}" in source
    assert "patchSelectedNodeData({ iterator_selector: selectorFromText(event.target.value) })" in source
    assert 'value={dataTextValue(selectedNodeData, "item_template")}' in source
    assert "patchSelectedNodeData({ item_template: event.target.value })" in source
    assert 'selectedNode.type === "document_extractor"' in source
    assert "value={selectorText(selectedNodeData.variable_selector)}" in source
    assert "patchSelectedNodeData({ variable_selector: selectorFromText(event.target.value) })" in source
    assert 'placeholder={t("workflowPlugin.editor.graph.documentPath")}' in source
    assert 'value={dataTextValue(selectedNodeData, "output_key")}' in source
    assert "patchSelectedNodeData({ output_key: event.target.value })" in source


def test_workflow_panel_exposes_tool_and_http_field_controls() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "function objectList" in source
    assert "function descriptorRowTextValue" in source
    assert "function toolConfigurationFallback" in source
    assert "function httpHeaderFallback" in source
    assert "function httpQueryFallback" in source
    assert 'selectedNode.type === "tool_call"' in source
    assert 'value={dataTextValue(selectedNodeData, "tool_name")}' in source
    assert "patchSelectedNodeData({ tool_name: event.target.value })" in source
    assert "objectRows(selectedNodeData.tool_configurations, toolConfigurationFallback()).map((configuration, configurationIndex)" in source
    assert "tool_configurations: objectRowsWithAddedRow(selectedNodeData.tool_configurations, toolConfigurationFallback())" in source
    assert 'tool_configurations: objectRowsWithValue(selectedNodeData.tool_configurations, configurationIndex, toolConfigurationFallback(), "name", event.target.value)' in source
    assert 'tool_configurations: objectRowsWithValue(selectedNodeData.tool_configurations, configurationIndex, toolConfigurationFallback(), "value", event.target.value)' in source
    assert 'tool_configurations: objectRowsWithValue(selectedNodeData.tool_configurations, configurationIndex, toolConfigurationFallback(), "value_selector", selectorFromText(event.target.value))' in source
    assert "tool_configurations: objectRowsWithoutIndex(selectedNodeData.tool_configurations, configurationIndex, toolConfigurationFallback())" in source
    assert "disabled={disabled || objectRows(selectedNodeData.tool_configurations, toolConfigurationFallback()).length <= 1}" in source
    assert 'selectedNode.type === "http_request"' in source
    assert 'value={dataTextValue(selectedNodeData, "request_method") || "GET"}' in source
    assert "patchSelectedNodeData({ request_method: event.target.value })" in source
    assert 'value={dataTextValue(selectedNodeData, "endpoint")}' in source
    assert "patchSelectedNodeData({ endpoint: event.target.value })" in source
    assert "function structuredValueText" in source
    assert "function structuredValueFromText" in source
    assert "function httpRequestBodyText" in source
    assert "function httpRequestBodyPatch" in source
    assert "function recordValue" in source
    assert "function httpAuthorizationValue" in source
    assert "function httpCredentialRefText" in source
    assert "function httpAuthorizationTextValue" in source
    assert "function httpCredentialRefPatch" in source
    assert "function httpAuthorizationPatch" in source
    assert "value={httpCredentialRefText(selectedNodeData)}" in source
    assert "patchSelectedNodeData(httpCredentialRefPatch(event.target.value))" in source
    assert 'title={t("workflowPlugin.editor.graph.httpCredentialRef")}' in source
    assert 'value={httpAuthorizationTextValue(selectedNodeData, "type") || "bearer"}' in source
    assert "patchSelectedNodeData(httpAuthorizationPatch(selectedNodeData, { type: event.target.value }))" in source
    assert 'title={t("workflowPlugin.editor.graph.httpAuthType")}' in source
    assert 'value={httpAuthorizationTextValue(selectedNodeData, "header_name")}' in source
    assert "patchSelectedNodeData(httpAuthorizationPatch(selectedNodeData, { header_name: event.target.value, headerName: undefined, header: undefined, name: undefined }))" in source
    assert 'title={t("workflowPlugin.editor.graph.httpAuthHeader")}' in source
    assert 'value={httpAuthorizationTextValue(selectedNodeData, "prefix")}' in source
    assert "patchSelectedNodeData(httpAuthorizationPatch(selectedNodeData, { prefix: event.target.value, value_prefix: undefined, valuePrefix: undefined }))" in source
    assert 'title={t("workflowPlugin.editor.graph.httpAuthPrefix")}' in source
    assert "objectRows(selectedNodeData.header_parameters, httpHeaderFallback()).map((header, headerIndex)" in source
    assert "header_parameters: objectRowsWithAddedRow(selectedNodeData.header_parameters, httpHeaderFallback())" in source
    assert 'header_parameters: objectRowsWithValue(selectedNodeData.header_parameters, headerIndex, httpHeaderFallback(), "name", event.target.value)' in source
    assert 'header_parameters: objectRowsWithValue(selectedNodeData.header_parameters, headerIndex, httpHeaderFallback(), "value", event.target.value)' in source
    assert "header_parameters: objectRowsWithoutIndex(selectedNodeData.header_parameters, headerIndex, httpHeaderFallback())" in source
    assert "disabled={disabled || objectRows(selectedNodeData.header_parameters, httpHeaderFallback()).length <= 1}" in source
    assert "objectRows(selectedNodeData.query_parameters, httpQueryFallback()).map((queryParameter, queryIndex)" in source
    assert "query_parameters: objectRowsWithAddedRow(selectedNodeData.query_parameters, httpQueryFallback())" in source
    assert 'query_parameters: objectRowsWithValue(selectedNodeData.query_parameters, queryIndex, httpQueryFallback(), "name", event.target.value)' in source
    assert 'query_parameters: objectRowsWithValue(selectedNodeData.query_parameters, queryIndex, httpQueryFallback(), "value", event.target.value)' in source
    assert "query_parameters: objectRowsWithoutIndex(selectedNodeData.query_parameters, queryIndex, httpQueryFallback())" in source
    assert "disabled={disabled || objectRows(selectedNodeData.query_parameters, httpQueryFallback()).length <= 1}" in source
    assert "value={httpRequestBodyText(selectedNodeData)}" in source
    assert "patchSelectedNodeData(httpRequestBodyPatch(event.target.value))" in source
    assert 't("workflowPlugin.editor.graph.requestBodyJsonOrTemplate")' in source


def test_workflow_panel_exposes_text_prompt_and_knowledge_field_controls() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "function stringListText" in source
    assert "function stringListFromText" in source
    assert "function llmModelValue" in source
    assert "function llmModelTextValue" in source
    assert "function llmTextValue" in source
    assert "function llmModelPatch" in source
    assert "function LlmSettingsFields" in source
    assert "function knowledgeFilterPatch" in source
    assert source.count("<LlmSettingsFields data={selectedNodeData} onPatch={patchSelectedNodeData} disabled={disabled} />") >= 3
    assert 'selectedNode.type === "answer"' in source
    assert 'value={dataTextValue(selectedNodeData, "answer")}' in source
    assert "patchSelectedNodeData({ answer: event.target.value })" in source
    assert 'selectedNode.type === "llm"' in source
    assert 'value={dataTextValue(selectedNodeData, "prompt_template")}' in source
    assert "patchSelectedNodeData({ prompt_template: event.target.value })" in source
    assert 'selectedNode.type === "parameter_extractor"' in source
    assert 'selectedNode.type === "question_classifier"' in source
    assert 'value={llmModelTextValue(data, "provider")}' in source
    assert "onPatch(llmModelPatch(data, { provider: event.target.value }))" in source
    assert 'title={t("workflowPlugin.editor.graph.llmProviderTitle")}' in source
    assert 'value={llmModelTextValue(data, "name")}' in source
    assert "onPatch(llmModelPatch(data, { name: event.target.value, model: undefined }))" in source
    assert 'title={t("workflowPlugin.editor.graph.llmModelNameTitle")}' in source
    assert 'value={llmModelTextValue(data, "provider_credential_id")}' in source
    assert "onPatch(llmModelPatch(data, { provider_credential_id: event.target.value, providerCredentialId: undefined }))" in source
    assert 'title={t("workflowPlugin.editor.graph.providerCredentialIdTitle")}' in source
    assert "value={httpCredentialRefText(data)}" in source
    assert "onPatch(httpCredentialRefPatch(event.target.value))" in source
    assert 'title={t("workflowPlugin.editor.graph.llmCredentialRefTitle")}' in source
    assert 'value={llmTextValue(data, "temperature")}' in source
    assert "onPatch({ temperature: structuredValueFromText(event.target.value) })" in source
    assert 'title={t("workflowPlugin.editor.graph.llmTemperatureTitle")}' in source
    assert 'value={llmTextValue(data, "max_tokens")}' in source
    assert "onPatch({ max_tokens: structuredValueFromText(event.target.value), maxTokens: undefined })" in source
    assert 'title={t("workflowPlugin.editor.graph.llmMaxTokensTitle")}' in source
    assert 'selectedNode.type === "template_transform"' in source
    assert 'value={dataTextValue(selectedNodeData, "template")}' in source
    assert "patchSelectedNodeData({ template: event.target.value })" in source
    assert 'selectedNode.type === "knowledge_retrieval"' in source
    assert "value={selectorText(selectedNodeData.query_variable_selector)}" in source
    assert "patchSelectedNodeData({ query_variable_selector: selectorFromText(event.target.value) })" in source
    assert "value={stringListText(selectedNodeData.dataset_ids)}" in source
    assert "patchSelectedNodeData({ dataset_ids: stringListFromText(event.target.value) })" in source
    assert 'value={llmTextValue(selectedNodeData, "top_k")}' in source
    assert "patchSelectedNodeData({ top_k: structuredValueFromText(event.target.value), topK: undefined })" in source
    assert 'title={t("workflowPlugin.editor.graph.knowledgeTopK")}' in source
    assert 'value={llmTextValue(selectedNodeData, "score_threshold")}' in source
    assert "patchSelectedNodeData({ score_threshold: structuredValueFromText(event.target.value), scoreThreshold: undefined })" in source
    assert 'title={t("workflowPlugin.editor.graph.knowledgeScoreThreshold")}' in source
    assert "value={structuredValueText(selectedNodeData.dataset_filter ?? selectedNodeData.datasetFilter)}" in source
    assert 'patchSelectedNodeData(knowledgeFilterPatch("dataset_filter", event.target.value))' in source
    assert 'title={t("workflowPlugin.editor.graph.knowledgeDatasetFilter")}' in source
    assert "value={structuredValueText(selectedNodeData.metadata_filter ?? selectedNodeData.metadataFilter)}" in source
    assert 'patchSelectedNodeData(knowledgeFilterPatch("metadata_filter", event.target.value))' in source
    assert 'title={t("workflowPlugin.editor.graph.knowledgeMetadataFilter")}' in source
    assert 'value={dataTextValue(selectedNodeData, "output_key")}' in source
    assert "patchSelectedNodeData({ output_key: event.target.value })" in source


def test_workflow_panel_exposes_sub_workflow_field_controls() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert '"sub_workflow"' in source
    assert 'if (type === "sub_workflow")' in source
    assert 'workflow_id: ""' in source
    assert 'version_id: ""' in source
    assert 'inputs: { message: "{{message}}" }' in source
    assert "workflowOptions: WorkflowSummary[]" in source
    assert "currentWorkflowId?: string | null" in source
    assert "const childWorkflowOptions = workflowOptions.filter((workflow) => workflow.workflow_id !== currentWorkflowId)" in source
    assert "workflowOptions={workflows}" in source
    assert "currentWorkflowId={selectedWorkflow?.workflow_id}" in source
    assert 'selectedNode.type === "sub_workflow"' in source
    assert 'title={t("workflowPlugin.editor.graph.childWorkflow")}' in source
    assert '<option value="">{t("workflowPlugin.editor.graph.selectChildWorkflow")}</option>' in source
    assert "childWorkflowOptions.map" in source
    assert "{workflow.name} ({workflow.status})" in source
    assert 'value={dataTextValue(selectedNodeData, "workflow_id")}' in source
    assert "patchSelectedNodeData({ workflow_id: event.target.value })" in source
    assert 'value={dataTextValue(selectedNodeData, "version_id")}' in source
    assert "patchSelectedNodeData({ version_id: event.target.value })" in source
    assert "value={assignmentEntryName(selectedNodeData.inputs)}" in source
    assert "patchSelectedNodeData({ inputs: assignmentsWithEntryName(selectedNodeData.inputs, event.target.value) })" in source
    assert "value={assignmentEntryTextValue(selectedNodeData.inputs)}" in source
    assert "patchSelectedNodeData({ inputs: assignmentsWithEntryValue(selectedNodeData.inputs, event.target.value) })" in source
    assert 'placeholder={t("workflowPlugin.editor.graph.childWorkflowId")}' in source
    assert 'placeholder={t("workflowPlugin.editor.graph.pinnedVersionId")}' in source


def test_workflow_panel_exposes_logic_node_field_controls() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "function firstObjectTextValue" in source
    assert "function objectListWithFirstValue" in source
    assert "function assignmentEntryName" in source
    assert "function assignmentEntryRawValue" in source
    assert "function assignmentEntryTextValue" in source
    assert "function assignmentsWithEntryName" in source
    assert "function assignmentsWithEntryValue" in source
    assert "function objectRows" in source
    assert "function objectRowTextValue" in source
    assert "function objectRowsWithValue" in source
    assert "function objectRowsWithAddedRow" in source
    assert "function objectRowsWithoutIndex" in source
    assert "function conditionCaseFallback" in source
    assert "function conditionCaseRows" in source
    assert "function conditionCaseId" in source
    assert "function conditionCaseCondition" in source
    assert "function conditionCaseConditionValue" in source
    assert "function conditionCasesPatch" in source
    assert "function conditionCasesWithCaseId" in source
    assert "function conditionCasesWithConditionValue" in source
    assert "function conditionCasesWithAddedCase" in source
    assert "function conditionCasesWithoutIndex" in source
    assert "const CONDITION_BRANCH_HANDLES" in source
    assert 'selectedNode.type === "condition"' in source
    assert 'firstObjectTextValue(selectedNodeData.conditions, "variable")' in source
    assert 'objectListWithFirstValue(selectedNodeData.conditions, { variable: "message", operator: "not_empty" }, "variable", event.target.value)' in source
    assert 'objectListWithFirstValue(selectedNodeData.conditions, { variable: "message", operator: "not_empty" }, "operator", event.target.value)' in source
    assert 'objectListWithFirstValue(selectedNodeData.conditions, { variable: "message", operator: "not_empty" }, "value", event.target.value)' in source
    assert "CONDITION_BRANCH_HANDLES.map((branchHandle) => {" in source
    assert "const branchEdge = edgeForSourceHandle(edges, selectedNode.id, branchHandle)" in source
    assert 'title={t("workflowPlugin.editor.graph.branchTargetFor", { handle: branchHandle })}' in source
    assert "onUpdateEdge(branchEdge.id, { target, source_handle: branchHandle })" in source
    assert "onAddEdge(selectedNode.id, target, branchHandle)" in source
    assert 'title={t("workflowPlugin.editor.graph.addCaseBranch")}' in source
    assert "conditionCaseRows(selectedNodeData).map((conditionCase, caseIndex) => {" in source
    assert "const caseId = conditionCaseId(conditionCase, caseIndex)" in source
    assert "const caseEdge = edgeForSourceHandle(edges, selectedNode.id, caseId)" in source
    assert "conditionCasesPatch(conditionCasesWithAddedCase(selectedNodeData))" in source
    assert "conditionCasesPatch(conditionCasesWithCaseId(selectedNodeData, caseIndex, event.target.value))" in source
    assert "conditionCasesWithConditionValue(selectedNodeData, caseIndex, \"variable_selector\", selectorFromText(event.target.value))" in source
    assert "conditionCasesWithConditionValue(selectedNodeData, caseIndex, \"operator\", event.target.value)" in source
    assert "conditionCasesWithConditionValue(selectedNodeData, caseIndex, \"value\", event.target.value)" in source
    assert 'title={t("workflowPlugin.editor.graph.caseBranchTarget")}' in source
    assert 'value={caseEdge?.target || ""}' in source
    assert "onUpdateEdge(caseEdge.id, { target, source_handle: caseId })" in source
    assert "onAddEdge(selectedNode.id, target, caseId)" in source
    assert "conditionCasesPatch(conditionCasesWithoutIndex(selectedNodeData, caseIndex))" in source
    assert '"human_approval"' in source
    assert 'if (type === "human_approval")' in source
    assert "instructions: defaultText.approveInstruction" in source
    assert 'output_key: "approval"' in source
    assert 'selectedNode.type === "human_approval"' in source
    assert 'value={dataTextValue(selectedNodeData, "instructions")}' in source
    assert "patchSelectedNodeData({ instructions: event.target.value })" in source
    assert 't("workflowPlugin.editor.approval.instructionsTitle")' in source
    assert 'value={dataTextValue(selectedNodeData, "assignee")}' in source
    assert "patchSelectedNodeData({ assignee: event.target.value })" in source
    assert 't("workflowPlugin.editor.approval.assigneeTitle")' in source
    assert 'value={dataTextValue(selectedNodeData, "output_key")}' in source
    assert "patchSelectedNodeData({ output_key: event.target.value })" in source
    assert 't("workflowPlugin.editor.approval.outputKeyTitle")' in source
    assert 'selectedNode.type === "variable_assign"' in source
    assert "value={assignmentEntryName(selectedNodeData.assignments)}" in source
    assert "patchSelectedNodeData({ assignments: assignmentsWithEntryName(selectedNodeData.assignments, event.target.value) })" in source
    assert "value={assignmentEntryTextValue(selectedNodeData.assignments)}" in source
    assert "patchSelectedNodeData({ assignments: assignmentsWithEntryValue(selectedNodeData.assignments, event.target.value) })" in source
    assert 'selectedNode.type === "variable_aggregator"' in source
    assert "const VARIABLE_AGGREGATOR_SELECTOR_KEYS" in source
    assert "const VARIABLE_AGGREGATOR_WRAPPER_KEYS" in source
    assert "const VARIABLE_AGGREGATOR_CLEAR_KEYS" in source
    assert "function variableAggregatorSelectorRows" in source
    assert "function variableAggregatorSelectorRowsFromValue" in source
    assert 'value.every((item) => typeof item === "string" || typeof item === "number")' in source
    assert "function variableAggregatorSelectorsWithValue" in source
    assert "function variableAggregatorSelectorsWithAddedSelector" in source
    assert "function variableAggregatorSelectorsWithoutIndex" in source
    assert "function variableAggregatorSelectorPatch" in source
    assert "variableAggregatorSelectorRows(selectedNodeData).map((selector, selectorIndex)" in source
    assert "patchSelectedNodeData(variableAggregatorSelectorPatch(variableAggregatorSelectorsWithAddedSelector(selectedNodeData)))" in source
    assert "variableAggregatorSelectorsWithValue(selectedNodeData, selectorIndex, selectorFromText(event.target.value))" in source
    assert "variableAggregatorSelectorsWithoutIndex(selectedNodeData, selectorIndex)" in source
    assert "disabled={disabled || variableAggregatorSelectorRows(selectedNodeData).length <= 1}" in source
    assert 'patchSelectedNodeData({ mode: event.target.value })' in source
    assert 'selectedNode.type === "parameter_extractor"' in source
    assert "function parameterExtractorParameterFallback" in source
    assert "objectRows(selectedNodeData.parameters, parameterExtractorParameterFallback()).map((parameter, parameterIndex)" in source
    assert "parameters: objectRowsWithAddedRow(selectedNodeData.parameters, parameterExtractorParameterFallback())" in source
    assert 'parameters: objectRowsWithValue(selectedNodeData.parameters, parameterIndex, parameterExtractorParameterFallback(), "name", event.target.value)' in source
    assert 'parameters: objectRowsWithValue(selectedNodeData.parameters, parameterIndex, parameterExtractorParameterFallback(), "type", event.target.value)' in source
    assert 'parameters: objectRowsWithValue(selectedNodeData.parameters, parameterIndex, parameterExtractorParameterFallback(), "description", event.target.value)' in source
    assert "parameters: objectRowsWithoutIndex(selectedNodeData.parameters, parameterIndex, parameterExtractorParameterFallback())" in source
    assert "disabled={disabled || objectRows(selectedNodeData.parameters, parameterExtractorParameterFallback()).length <= 1}" in source
    assert 'selectedNode.type === "question_classifier"' in source
    assert "function questionClassifierClassFallback" in source
    assert "function questionClassifierClassId" in source
    assert "function normalizedBranchHandle" in source
    assert "function edgeForSourceHandle" in source
    assert "objectRows(selectedNodeData.classes, questionClassifierClassFallback()).map((classifierClass, classIndex) => {" in source
    assert "const classId = questionClassifierClassId(classifierClass, classIndex)" in source
    assert "const classEdge = edgeForSourceHandle(edges, selectedNode.id, classId)" in source
    assert "classes: objectRowsWithAddedRow(selectedNodeData.classes, questionClassifierClassFallback())" in source
    assert 'classes: objectRowsWithValue(selectedNodeData.classes, classIndex, questionClassifierClassFallback(), "id", event.target.value)' in source
    assert 'classes: objectRowsWithValue(selectedNodeData.classes, classIndex, questionClassifierClassFallback(), "name", event.target.value)' in source
    assert 'title={t("workflowPlugin.editor.graph.classBranchTarget")}' in source
    assert 'value={classEdge?.target || ""}' in source
    assert "onUpdateEdge(classEdge.id, { target, source_handle: classId })" in source
    assert "onAddEdge(selectedNode.id, target, classId)" in source
    assert "classes: objectRowsWithoutIndex(selectedNodeData.classes, classIndex, questionClassifierClassFallback())" in source
    assert "disabled={disabled || objectRows(selectedNodeData.classes, questionClassifierClassFallback()).length <= 1}" in source


def test_workflow_panel_preserves_node_title_when_saving_graph_dsl() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    spread_index = source.index("...(node.data || {})")
    title_index = source.index("title: node.title || node.id", spread_index)
    assert spread_index < title_index


def test_workflow_panel_exposes_editable_edge_controls() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "onUpdateEdge" in source
    assert "onUpdateEdge: (edgeId: string, patch: Partial<GraphEdge>) => void" in source
    assert "const handleUpdateEdge = (edgeId: string, patch: Partial<GraphEdge>)" in source
    assert "edges: current.edges.map((edge) => (edge.id === edgeId ? { ...edge, ...patch } : edge))" in source
    assert "onUpdateEdge={handleUpdateEdge}" in source
    assert 'data-testid={`workflow-node-card-${node.id || index}`}' in source
    assert 'data-testid={`workflow-edge-card-${edge.id || `${edge.source}-${edge.target}`}`}' in source
    assert 'placeholder={t("workflowPlugin.editor.graph.sourceHandle")}' in source
    assert 'data-testid={`workflow-edge-source-handle-${edge.id || `${edge.source}-${edge.target}`}`}' in source
    assert "onUpdateEdge(edge.id || \"\", { source_handle: event.target.value || null })" in source
    assert 'title={t("workflowPlugin.editor.graph.targetNode")}' in source
    assert 'data-testid={`workflow-edge-target-${edge.id || `${edge.source}-${edge.target}`}`}' in source
    assert "onUpdateEdge(edge.id || \"\", { target: event.target.value })" in source
    assert 'placeholder={t("workflowPlugin.editor.graph.targetHandle")}' in source
    assert 'data-testid={`workflow-edge-target-handle-${edge.id || `${edge.source}-${edge.target}`}`}' in source
    assert "onUpdateEdge(edge.id || \"\", { target_handle: event.target.value || null })" in source
    assert 'data-testid={`workflow-add-edge-target-${selectedNode.id}`}' in source
    assert "edge.valid === false" in source
    assert 't("workflowPlugin.editor.graph.noEdges")' in source
    assert "sourceHandle: edge.source_handle || undefined" in source
    assert "targetHandle: edge.target_handle || undefined" in source


def test_workflow_panel_validates_graph_before_saving() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "function validateEditableGraph" in source
    assert "Node id \"${nodeId}\" is duplicated." in source
    assert "Graph must include one start node." in source
    assert "Graph can include only one start node." in source
    assert "Edge ${label} is marked invalid." in source
    assert "Edge ${label} source \"${source}\" does not exist." in source
    assert "Edge ${label} target \"${target}\" does not exist." in source
    assert "const nodeTypesById = new Map<string, string>();" in source
    assert "nodeTypesById.set(nodeId, nodeType);" in source
    assert "function workflowEdgeBoundaryIssue" in source
    assert "Edge ${label} targets entry node \"${target}\"." in source
    assert "const targetType = nodeTypesById.get(target);" in source
    assert 'sourceType === "end" || (sourceType === "answer" && targetType !== "end")' in source
    assert "Edge ${label} starts from exit node \"${source}\"." in source
    assert "const graphIssues = useMemo(() => validateEditableGraph(editableGraph), [editableGraph])" in source
    assert "graphIssues={graphIssues}" in source
    assert "graphIssues: string[]" in source
    assert "Graph issues" in source
    assert "graphIssues.map((issue)" in source
    assert "const issues = validateEditableGraph(graphToSave)" in source
    assert "Fix graph issues before saving: ${issues[0]}" in source
    assert "return;" in source


def test_workflow_canvas_rejects_boundary_violating_connections_immediately() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "const boundaryIssue = workflowEdgeBoundaryIssue(nodeTypesById, source, target, \"connection\")" in source
    assert "toast.error(boundaryIssue)" in source
    assert "return current;" in source
    assert "edges: [" in source
    assert "source_handle: sourceHandle || null" in source
    assert "target_handle: null" in source


def test_workflow_panel_generates_unique_ids_for_added_nodes() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "function nextWorkflowNodeId(graph: EditableGraph)" in source
    assert 'const existingIds = new Set(graph.nodes.map((node) => (node.id || "").trim()).filter(Boolean));' in source
    assert 'const match = /^node_(\\d+)$/.exec((node.id || "").trim());' in source
    assert "Math.max(graph.nodes.length + 1, highestGeneratedNumber + 1)" in source
    assert "while (existingIds.has(`node_${nextNumber}`))" in source
    assert "return `node_${nextNumber}`;" in source
    assert "const id = nextWorkflowNodeId(current);" in source
    assert "const id = `node_${nextNumber}`;" not in source
    assert "onAddNodeAt={(nodeType, position, presetId) => onAddNode(nodeType, position, presetId)}" in source


def test_workflow_panel_supports_canvas_drop_from_node_palette() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert 'const WORKFLOW_CANVAS_DRAG_TYPE = "application/x-lambchat-workflow-node";' in source
    assert "const handleDragStart = (" in source
    assert "event.dataTransfer.setData(" in source
    assert "JSON.stringify({ nodeType, presetId })" in source
    assert 'event.dataTransfer.effectAllowed = "copy"' in source
    assert "const handleDrop = useCallback(" in source
    assert "Array.from(event.dataTransfer.types).includes(WORKFLOW_CANVAS_DRAG_TYPE)" in source
    assert "const rawPayload = event.dataTransfer.getData(WORKFLOW_CANVAS_DRAG_TYPE)" in source
    assert "reactFlowInstanceRef.current?.screenToFlowPosition" in source
    assert "onAddNodeAt(" in source
    assert "onDragOver={handleDragOver}" in source
    assert "onDrop={handleDrop}" in source


def test_workflow_panel_exposes_backend_preflight_validation() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")
    api_source = (REPO_ROOT / "frontend" / "src" / "plugins" / "workflow" / "api.ts").read_text(
        encoding="utf-8"
    )

    assert "export type WorkflowValidationResponse" in api_source
    assert "validate(" in api_source
    assert "/validate`" in api_source
    assert "const [isValidating, setIsValidating] = useState(false)" in source
    assert "const handleValidate = async () =>" in source
    assert "workflowApi.validate(" in source
    assert 't("workflowPlugin.editor.toast.preflightPassed", { count: response.reachable_node_ids.length })' in source
    assert 't("workflowPlugin.editor.toast.preflightFailed", {' in source
    assert 't("workflowPlugin.editor.toast.workflowNotRunnable")' in source
    assert "onClick={handleValidate}" in source
    assert 't("workflowPlugin.editor.run.preflight")' in source
    assert "function BoundaryPreflightPanel" in source
    assert "function boundaryPreflightErrors" in source
    assert "function boundaryPreflightMessage" in source
    assert 't("workflowPlugin.editor.boundaryIssues.title")' in source
    assert 'error.startsWith("workflow_boundary_edge_")' in source
    assert 'error.startsWith("boundary_edge_")' in source
    assert "Edge ${edgeId} points back into the workflow entry" in source
    assert "Edge ${edgeId} starts from a workflow exit" in source
    assert "<BoundaryPreflightPanel report={normalizedReport} />" in source


def test_workflow_panel_displays_credential_preflight_metadata() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")
    api_source = (REPO_ROOT / "frontend" / "src" / "plugins" / "workflow" / "api.ts").read_text(
        encoding="utf-8"
    )

    assert "credential_refs_resolved: Array<Record<string, unknown>>" in api_source
    assert "credential_refs_unresolved: string[]" in api_source
    assert "function CredentialPreflightPanel" in source
    assert 't("workflowPlugin.editor.credentials.preflight")' in source
    assert "report.credential_refs_required" in source
    assert "report.credential_refs_resolved" in source
    assert "report.credential_refs_unresolved" in source
    assert '{resolved.length}/{required.length} {t("workflowPlugin.editor.common.mapped")}' in source
    assert "function reportWithValidationPreflight" in source
    assert "errors: uniqueWorkflowErrors([" in source
    assert "...validation.errors" in source
    assert "const normalizedReport = normalizeWorkflowImportReport(report) ?? report" in source
    assert "lossless: normalizedReport.lossless && validation.runnable" in source
    assert "...reportList(normalizedReport.errors).filter((error) => !error.startsWith(\"workflow_\"))" in source
    assert "credential_refs_required: validation.credential_refs_required" in source
    assert "credential_refs_resolved: validation.credential_refs_resolved" in source
    assert "credential_refs_unresolved: validation.credential_refs_unresolved" in source
    assert "reportWithValidationPreflight(current, response)" in source
    assert "<CredentialPreflightPanel report={normalizedReport} />" in source


def test_workflow_panel_normalizes_sparse_compatibility_reports() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "function normalizeWorkflowImportReport(value: unknown): WorkflowImportReport | null" in source
    assert "if (!value || typeof value !== \"object\" || Array.isArray(value)) return null" in source
    assert "source: \"workflow\"" in source
    assert "supported_nodes: reportList(report.supported_nodes)" in source
    assert "unsupported_nodes: reportObjectList(report.unsupported_nodes)" in source
    assert "credential_refs_required: reportList(report.credential_refs_required)" in source
    assert "credential_refs_resolved: reportMappingList(report.credential_refs_resolved)" in source
    assert "credential_refs_unresolved: reportList(report.credential_refs_unresolved)" in source
    assert "warnings: reportList(report.warnings)" in source
    assert "errors: reportList(report.errors)" in source
    assert "lossless: report.lossless === true" in source
    assert "const normalizedReport = normalizeWorkflowImportReport(report)" in source
    assert "normalizedReport.supported_nodes.length" in source
    assert "normalizedReport.unsupported_nodes.length" in source
    assert "normalizedReport.warnings.length" in source
    assert "normalizedReport.errors.length" in source
    assert "setReport(normalizeWorkflowImportReport(latestReport))" in source
    assert "setReport(normalizeWorkflowImportReport(response.compatibility_report))" in source


def test_workflow_panel_exposes_credential_vault_crud_controls() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")
    api_source = (REPO_ROOT / "frontend" / "src" / "plugins" / "workflow" / "api.ts").read_text(
        encoding="utf-8"
    )

    assert "export type WorkflowCredentialResponse" in api_source
    assert "credentials(skip = 0, limit = 50)" in api_source
    assert "upsertCredential(input" in api_source
    assert "deleteCredential(credentialId" in api_source
    assert "type CredentialDraft" in source
    assert "function CredentialVaultPanel" in source
    assert 't("workflowPlugin.editor.credentials.title")' in source
    assert "const [credentials, setCredentials] = useState<WorkflowCredentialResponse[]>([])" in source
    assert "const loadCredentials = useCallback(async () =>" in source
    assert "workflowApi.credentials(0, 100)" in source
    assert "const handleSaveCredential = async () =>" in source
    assert "workflowApi.upsertCredential" in source
    assert "const handleDeleteCredential = async (credentialId: string)" in source
    assert "workflowApi.deleteCredential(credentialId)" in source
    assert "credentialRefsFromReport(report)" in source
    assert "credentialDraftFromRef(ref)" in source
    assert "credentialDraftFromCredential(credential)" in source
    assert "<CredentialVaultPanel" in source
    assert "type=\"password\"" in source
    assert 't("workflowPlugin.editor.credentials.secretPlaceholder")' in source


def test_workflow_panel_exposes_pending_approval_inbox() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")
    api_source = (REPO_ROOT / "frontend" / "src" / "plugins" / "workflow" / "api.ts").read_text(
        encoding="utf-8"
    )

    assert "export type WorkflowPendingApprovalListResponse" in api_source
    assert "pendingApprovals(skip = 0, limit = 20)" in api_source
    assert "/approvals/pending?${params}" in api_source
    assert "function PendingApprovalInbox" in source
    assert 't("workflowPlugin.editor.approval.pendingTitle")' in source
    assert "const [pendingApprovals, setPendingApprovals] = useState<WorkflowRunResponse[]>([])" in source
    assert "workflowApi.pendingApprovals(0, 20)" in source
    assert "const loadPendingApprovals = useCallback(async () =>" in source
    assert "const handleSelectPendingApproval = async (run: WorkflowRunResponse) =>" in source
    assert "setSelectedId(run.workflow_id)" in source
    assert "workflowApi.runEvents(run.workflow_id, run.run_id)" in source
    assert "<PendingApprovalInbox" in source


def test_workflow_panel_shows_loading_state_for_selected_run_events() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "function RunEventsPanel({" in source
    assert "events: WorkflowRunEvent[]" in source
    assert "function workflowRunEvents(value: unknown): WorkflowRunEvent[]" in source
    assert "isLoading: boolean" in source
    assert 'isLoading ? t("workflowPlugin.editor.events.loading") : focusedNodeId ? `${focusedNodeEventCount}/${events.length}` : events.length' in source
    assert 't("workflowPlugin.editor.events.loadingDetail")' in source
    assert "const [isLoadingRunEvents, setIsLoadingRunEvents] = useState(false)" in source
    assert "disabled={!run.run_id || isLoadingRunEvents}" in source
    assert "<RunEventsPanel" in source
    assert "events={runEvents}" in source
    assert "isLoading={isLoadingRunEvents}" in source

    select_run_start = source.index("const handleSelectRun = async (run: WorkflowRunResponse) =>")
    select_pending_start = source.index("const handleSelectPendingApproval = async (run: WorkflowRunResponse)")
    select_run_source = source[select_run_start:select_pending_start]
    assert "setRunResult(run)" in select_run_source
    assert "setRunEvents([])" in select_run_source
    assert "setIsLoadingRunEvents(true)" in select_run_source
    assert "workflowApi.runEvents(selectedWorkflow.workflow_id, run.run_id)" in select_run_source
    assert "setRunEvents(workflowRunEvents(eventResponse.events))" in select_run_source
    assert "setIsLoadingRunEvents(false)" in select_run_source
    assert select_run_source.index("setRunEvents([])") < select_run_source.index("setIsLoadingRunEvents(true)")
    assert select_run_source.index("setIsLoadingRunEvents(true)") < select_run_source.index("workflowApi.runEvents")
    assert select_run_source.index("setIsLoadingRunEvents(false)") > select_run_source.index("catch (error)")

    select_pending_end = source.index("return (", select_pending_start)
    select_pending_source = source[select_pending_start:select_pending_end]
    assert "setSelectedId(run.workflow_id)" in select_pending_source
    assert "setRunResult(run)" in select_pending_source
    assert "setRunEvents([])" in select_pending_source
    assert "setApprovalComment(\"\")" in select_pending_source
    assert "setIsLoadingRunEvents(true)" in select_pending_source
    assert "workflowApi.runEvents(run.workflow_id, run.run_id)" in select_pending_source
    assert "setRunEvents(workflowRunEvents(eventResponse.events))" in select_pending_source
    assert "setIsLoadingRunEvents(false)" in select_pending_source
    assert select_pending_source.index("setRunEvents([])") < select_pending_source.index("setIsLoadingRunEvents(true)")
    assert select_pending_source.index("setIsLoadingRunEvents(true)") < select_pending_source.index("workflowApi.runEvents")
    assert select_pending_source.index("setIsLoadingRunEvents(false)") > select_pending_source.index("catch (error)")


def test_workflow_panel_displays_persistent_load_error_banner() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "function errorMessage(error: unknown, fallback: string)" in source
    assert "const [loadError, setLoadError] = useState<string | null>(null)" in source
    assert "let shouldLoadPendingApprovals = false" in source
    assert "const [response, catalog] = await Promise.all([" in source
    assert "shouldLoadPendingApprovals = true" in source
    assert "if (shouldLoadPendingApprovals) {" in source
    assert "const approvals = await workflowApi.pendingApprovals(0, 20)" in source
    assert 'const message = errorMessage(error, t("workflowPlugin.editor.toast.loadWorkflowsFailed"))' in source
    assert "setLoadError(message)" in source
    assert "setLoadError(null)" in source
    assert 't("workflowPlugin.editor.inventory.serviceUnavailable", { error: loadError })' in source
    assert "title={loadError}" in source
    assert "onClick={loadWorkflows}" in source
    assert 't("workflowPlugin.editor.toolbar.retry")' in source

    bootstrap_start = source.index("const [response, catalog] = await Promise.all([")
    bootstrap_end = source.index("setLoadError(null)", bootstrap_start)
    bootstrap_block = source[bootstrap_start:bootstrap_end]
    assert "workflowApi.pendingApprovals" not in bootstrap_block
    spinner_stop = source.index("setIsLoading(false)", bootstrap_end)
    pending_refresh = source.index("const approvals = await workflowApi.pendingApprovals(0, 20)", spinner_stop)
    assert spinner_stop < pending_refresh


def test_workflow_panel_can_debug_selected_workflow_version() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")
    api_source = (REPO_ROOT / "frontend" / "src" / "plugins" / "workflow" / "api.ts").read_text(
        encoding="utf-8"
    )

    assert "versionId?: string | null" in api_source
    assert "version_id: versionId ?? null" in api_source
    assert "const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null)" in source
    assert "setSelectedVersionId(null)" in source
    assert "return detail.latest_version?.version_id ?? versions[0]?.version_id ?? null" in source
    assert "const versionId = savedWorkflowVersionId(response)" in source
    assert 't("workflowPlugin.editor.run.debugVersion")' in source
    assert "workflow-debug-version" in source
    assert "selectedVersionId ?? workflowDetail?.latest_version?.version_id" in source
    assert "function resolveDebugVersionId" in source
    assert "const handleSelectDebugVersion = async (versionId: string | null)" in source
    assert "workflowApi.inputSchema(workflowId, nextVersionId)" in source
    assert "workflowApi.inputSchema(" in source
    assert "setRunInput(runInputFromSchema(schema, defaultText))" in source
    assert "workflowApi.run(" in source
    assert 'data-testid="workflow-import-submit"' in source
    assert 'data-testid="workflow-save-graph"' in source
    assert 'data-testid="workflow-publish-latest"' in source
    assert 'data-testid="workflow-run-mode"' in source
    assert 'data-testid="workflow-run-version"' in source
    assert 't("workflowPlugin.editor.run.runVersion")' in source
    assert "onChange={(event) => handleSelectDebugVersion(event.target.value || null)}" in source
    assert "onClick={() => handleSelectDebugVersion(version.version_id)}" in source


def test_workflow_panel_exposes_stable_action_selectors() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert 'data-testid="workflow-import-dry-run"' in source
    assert 'data-testid="workflow-import-submit"' in source
    assert 'data-testid="workflow-save-version"' in source
    assert 'data-testid="workflow-save-graph"' in source
    assert 'data-testid="workflow-delete-selected"' in source
    assert "data-testid={`workflow-delete-${workflow.workflow_id}`}" in source
    assert 'data-testid="workflow-preflight"' in source
    assert 'data-testid="workflow-publish-latest"' in source
    assert 'data-testid="workflow-unpublish"' in source
    assert 'data-testid="workflow-run-mode"' in source
    assert 'data-testid="workflow-run-version"' in source
    assert 'data-testid="workflow-approval-approve"' in source
    assert 'data-testid="workflow-approval-reject"' in source


def test_workflow_panel_reduces_canvas_drag_flicker() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "animated: false" in source
    assert "const handleNodeDragStop = useCallback(" in source
    assert "onNodeDragStop={handleNodeDragStop}" in source
    assert "const [liveNodePositions, setLiveNodePositions]" in source
    assert "change.type === \"position\" && change.position" in source
    assert "change.dragging === false" in source
    assert "delete next[change.id]" in source
    assert "delete next[node.id]" in source
    assert "<ReactFlowProvider>" in source

    graph_editor_index = source.index("function GraphEditor(")
    provider_index = source.index("<ReactFlowProvider>", graph_editor_index)
    canvas_index = source.index("<WorkflowCanvas", provider_index)
    provider_end_index = source.index("</ReactFlowProvider>", canvas_index)
    assert graph_editor_index < provider_index < canvas_index < provider_end_index


def test_workflow_panel_clears_stale_run_event_focus_when_node_id_changes() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    handle_start = source.index("const handleUpdateNode = (nodeId: string, patch: Partial<GraphNode>) => {")
    handle_end = source.index("const handleResetNodeData", handle_start)
    handle_source = source[handle_start:handle_end]

    assert "setEditableGraph((current) => graphWithNodePatch(current, nodeId, patch))" in handle_source
    assert "setSelectedNodeId(patch.id)" in handle_source
    assert "setRunEventFocusedNodeId((current) => (current === nodeId ? null : current))" in handle_source
    assert 'data-testid="workflow-selected-node-id"' in source


def test_workflow_panel_applies_saved_version_boundary_immediately() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "type WorkflowImportResponse" in source
    assert "function inputSchemaFromIoContract" in source
    assert "function savedWorkflowVersionId(response: WorkflowImportResponse)" in source
    assert "response.interface?.entry?.version_id" in source
    assert "response.io_contract?.version_id" in source
    assert "const applySavedVersionBoundary = useCallback((response: WorkflowImportResponse) =>" in source
    assert "const schema = inputSchemaFromIoContract(response.io_contract)" in source
    assert "interface: contract.interface" in source
    assert "setIoContract(response.io_contract)" in source
    assert "setInputSchema(schema)" in source
    assert "setRunInput(runInputFromSchema(schema, defaultText))" in source
    assert "applySavedVersionBoundary(response)" in source
    assert "await refreshSelectedWorkflow(selectedWorkflow.workflow_id, savedWorkflowVersionId(response))" in source
    assert "}, [applySavedVersionBoundary, defaultText, loadWorkflows, navigate, workflowName])" in source


def test_workflow_panel_polls_or_streams_queued_async_runs() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "function isWorkflowRunWaiting" in source
    assert 'return status === "queued" || status === "running"' in source
    assert 'const responseRunId = typeof response.run_id === "string" && response.run_id ? response.run_id : null' in source
    assert 'const shouldStreamRun = runMode === "stream" && responseRunId !== null && isWorkflowRunWaiting(response.status)' in source
    assert 'const shouldPollRun = runMode === "async" && responseRunId !== null && isWorkflowRunWaiting(response.status)' in source
    assert "if (shouldStreamRun)" in source
    assert "} else if (shouldPollRun)" in source
    assert 'response.status === "running"' not in source


def test_workflow_panel_skips_pre_monitor_event_fetch_for_waiting_runs() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    stream_flag_index = source.index('const shouldStreamRun = runMode === "stream"')
    poll_flag_index = source.index('const shouldPollRun = runMode === "async"')
    event_fetch_guard_index = source.index(
        "if (inlineRunEvents.length === 0 && responseRunId && !shouldStreamRun && !shouldPollRun)",
        poll_flag_index,
    )
    stream_monitor_index = source.index("if (shouldStreamRun)", event_fetch_guard_index)
    assert stream_flag_index < event_fetch_guard_index < stream_monitor_index
    assert poll_flag_index < event_fetch_guard_index < stream_monitor_index
    assert 'toast.error(errorMessage(error, t("workflowPlugin.editor.toast.loadRunEventsFailed")))' in source


def test_workflow_panel_handles_stream_error_frames_as_failed_runs() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")
    api_source = (REPO_ROOT / "frontend" / "src" / "plugins" / "workflow" / "api.ts").read_text(
        encoding="utf-8"
    )

    assert "error?: string | null" in api_source
    assert "export type WorkflowRunEventStreamError" in api_source
    assert "onError?: (error: WorkflowRunEventStreamError) => void" in api_source
    assert 'eventName === "workflow_run_error"' in api_source
    assert "handlers.onError?.(payload as WorkflowRunEventStreamError)" in api_source
    assert "let streamErrorMessage: string | null = null" in source
    assert "onError: (streamError) =>" in source
    assert "streamErrorMessage = streamError.error" in source
    assert 'status: "failed"' in source
    assert "error: streamError.error" in source
    assert 'toast.error(streamError.error || t("workflowPlugin.editor.toast.workflowStreamFailed"))' in source
    error_guard_index = source.index("if (streamErrorMessage) {")
    final_refresh_index = source.index("const eventResponse = await workflowApi.runEvents(workflowId, runId)", error_guard_index)
    assert error_guard_index < final_refresh_index


def test_workflow_panel_surfaces_run_output_summary_before_raw_json() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "WORKFLOW_RUN_OUTPUT_PREVIEW_LIMIT" in source
    assert "type WorkflowRunOutputEntry" in source
    assert "function workflowRunOutputSummary" in source
    assert "outputFields: WorkflowInputField[] = []" in source
    assert "for (const field of outputFields)" in source
    assert "workflowOutputPathValue(rawOutput, field.field)" in source
    assert "function workflowRunOutputEntries" in source
    assert "outputFields: WorkflowInputField[] = []" in source
    assert "const contractByField = new Map(outputFields.map((field) => [field.field, field]))" in source
    assert "workflowOutputPathValue(rawOutput, key)" in source
    assert '"Not returned by this run"' in source
    assert "const outputSummary = workflowRunOutputSummary(run, outputFields)" in source
    assert "{outputSummary && (" in source
    assert "const outputSummary = workflowRunOutputSummary(runResult, outputFields)" in source
    assert "workflowRunOutputEntries(runResult, outputFields)" in source
    assert "schemaFieldsFromSchema(ioContract?.output_schema, { nested: true })" in source
    assert "prefix: `${fieldPath}[]`" in source
    assert "entry.declared" in source
    assert "contract" in source
    assert "entry.present" in source
    assert "missing" in source
    assert 't("workflowPlugin.editor.run.noOutput")' in source
    assert 't("workflowPlugin.editor.run.rawRunJson")' in source

    last_run_index = source.index('t("workflowPlugin.editor.run.lastRun")')
    raw_json_index = source.index('t("workflowPlugin.editor.run.rawRunJson")', last_run_index)
    json_index = source.index("JSON.stringify(runResult, null, 2)", last_run_index)
    assert last_run_index < raw_json_index < json_index


def test_workflow_panel_surfaces_run_interface_before_raw_json() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")
    api_source = (REPO_ROOT / "frontend" / "src" / "plugins" / "workflow" / "api.ts").read_text(
        encoding="utf-8"
    )

    assert "export type WorkflowRunInterface" in api_source
    assert "interface?: WorkflowRunInterface | null;" in api_source
    assert "export type WorkflowRunNextAction" in api_source
    assert "next_action?: WorkflowRunNextAction | null;" in api_source
    assert "type WorkflowRunInterfaceItem" in source
    assert "type WorkflowRunNextActionSummary" in source
    assert "function workflowRunInterfaceItems" in source
    assert "function workflowRunNextActionSummary" in source
    assert "workflowInterfaceObject(run?.interface)" in source
    assert "workflowInterfaceObject(run?.next_action)" in source
    assert "workflowInterfaceToolField(entry.tool, entry.argument)" in source
    assert 'label: "Entry"' in source
    assert 'label: "Exit"' in source
    assert 'label: "Debug"' in source
    assert "workflowInterfaceToolField(entry.schema_tool, entry.schema_field)" in source
    assert "workflowInterfaceToolField(exit.schema_tool, exit.schema_field)" in source
    assert "workflowInterfaceText(debug.run_id)" in source
    assert "workflowRunInterfaceItems(runResult).length > 0" in source
    assert "workflowRunNextActionSummary(runResult)" in source
    assert "workflowRunNextActionBadgeClass(nextAction.type)" in source
    assert "<GitBranch size={13} />" in source
    assert 't("workflowPlugin.editor.run.interface")' in source
    assert 't("workflowPlugin.editor.run.nextAction")' in source
    assert "title={`${item.label}: ${item.value} (${item.detail})`}" in source

    last_run_index = source.index('t("workflowPlugin.editor.run.lastRun")')
    interface_index = source.index('t("workflowPlugin.editor.run.interface")', last_run_index)
    next_action_index = source.index('t("workflowPlugin.editor.run.nextAction")', last_run_index)
    raw_json_index = source.index('t("workflowPlugin.editor.run.rawRunJson")', last_run_index)
    assert last_run_index < interface_index < next_action_index < raw_json_index


def test_workflow_import_response_types_include_saved_version_boundary() -> None:
    api_source = (REPO_ROOT / "frontend" / "src" / "plugins" / "workflow" / "api.ts").read_text(
        encoding="utf-8"
    )

    assert "export type WorkflowImportResponse" in api_source
    assert "io_contract?: WorkflowIoContractResponse | null;" in api_source
    assert "interface?: WorkflowRunInterface | null;" in api_source


def test_workflow_panel_contract_badge_prefers_required_output_field_paths() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "function workflowOutputContractMissingFields" in source
    assert "WorkflowRunResponse[\"output_contract\"]" in source
    assert "contract.required_field_paths" in source
    assert "const missingRoots = new Set(missing)" in source
    assert 'path.split(".", 1)[0]' in source
    assert 'replace(/\\[\\]$/, "")' in source
    assert "return missingPaths.length > 0 ? missingPaths : missing" in source
    assert "const missing = workflowOutputContractMissingFields(contract)" in source


def test_workflow_panel_marks_truncated_run_event_payloads_without_value_preview() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "function workflowEventPayloadTruncation" in source
    assert 'payload.reason !== "workflow_event_payload_too_large"' in source
    assert "function formatRunEventPayloadBytes" in source
    assert "originalBytes: runEventPayloadByteValue(payload.original_bytes)" in source
    assert "maxBytes: runEventPayloadByteValue(payload.max_bytes)" in source
    assert "keys: Array.isArray(payload.keys)" in source
    assert 't("workflowPlugin.editor.events.payloadTruncated")' in source
    assert 't("workflowPlugin.editor.events.payloadOriginalLimit", {' in source
    assert "original: formatRunEventPayloadBytes(selectedTruncation.originalBytes)" in source
    assert "limit: formatRunEventPayloadBytes(selectedTruncation.maxBytes)" in source
    assert 't("workflowPlugin.editor.events.payloadKeys", { keys: selectedTruncation.keys.join(", ") })' in source

    panel_start = source.index("function RunEventsPanel")
    panel_end = source.index("function HumanApprovalPanel", panel_start)
    panel_source = source[panel_start:panel_end]
    assert "const selectedTruncation = selectedEvent" in panel_source
    assert "workflowEventPayloadTruncation(selectedEvent.payload)" in panel_source
    assert "selectedTruncation.keys.join" in panel_source
    assert "value_preview" not in panel_source
    assert "payload_preview" not in panel_source


def test_workflow_panel_merges_run_events_without_duplicate_event_keys() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")

    assert "function mergeWorkflowRunEvents" in source
    assert "const seen = new Set(current.map((event) => event.event_id))" in source
    assert "if (seen.has(event.event_id)) return false" in source
    assert "left.sequence - right.sequence || left.event_id.localeCompare(right.event_id)" in source
    assert "setRunEvents((current) => mergeWorkflowRunEvents(current, [event]))" in source
    assert "setRunEvents((current) => mergeWorkflowRunEvents(current, resumeEvents))" in source

    resume_index = source.index("const resumeEvents = workflowRunEvents(response.events)")
    merge_index = source.index("setRunEvents((current) => mergeWorkflowRunEvents(current, resumeEvents))", resume_index)
    assert resume_index < merge_index


def test_workflow_api_can_fetch_version_scoped_input_schema() -> None:
    api_source = (REPO_ROOT / "frontend" / "src" / "plugins" / "workflow" / "api.ts").read_text(
        encoding="utf-8"
    )

    assert "inputSchema(" in api_source
    assert "versionId?: string | null" in api_source
    assert 'params.set("version_id", versionId)' in api_source
    assert "input-schema${query ? `?${query}` : \"\"}`" in api_source


def test_workflow_api_types_include_output_contract_field_paths() -> None:
    api_source = (REPO_ROOT / "frontend" / "src" / "plugins" / "workflow" / "api.ts").read_text(
        encoding="utf-8"
    )

    assert "output_contract?: {" in api_source
    assert "declared_fields?: string[];" in api_source
    assert "declared_field_paths?: string[];" in api_source
    assert "required_fields?: string[];" in api_source
    assert "required_field_paths?: string[];" in api_source


def test_workflow_version_option_renderer_uses_selected_workflow_context() -> None:
    option_source = (
        REPO_ROOT / "frontend" / "src" / "plugins" / "workflow" / "WorkflowSelectOption.tsx"
    ).read_text(encoding="utf-8")
    contract_source = CONTRACT_UTILS_SOURCE.read_text(encoding="utf-8")
    project_renderer_source = (
        REPO_ROOT / "frontend" / "src" / "components" / "sidebar" / "projectOptionRenderers.tsx"
    ).read_text(encoding="utf-8")
    scheduled_renderer_source = (
        REPO_ROOT
        / "frontend"
        / "src"
        / "components"
        / "panels"
        / "ScheduledTaskPanel"
        / "scheduledTaskOptionRenderers.tsx"
    ).read_text(encoding="utf-8")

    assert "export function WorkflowPluginVersionSelectOption" in option_source
    assert "WORKFLOW_ID_KEY_BY_VERSION_KEY" in option_source
    assert "DEFAULT_WORKFLOW_VERSION_ID: \"DEFAULT_WORKFLOW_ID\"" in option_source
    assert "SELECTED_WORKFLOW_VERSION_ID: \"SELECTED_WORKFLOW_ID\"" in option_source
    assert "WORKFLOW_VERSION_ID: \"WORKFLOW_ID\"" in option_source
    assert "VERSION_KEY_BY_WORKFLOW_ID_KEY" in option_source
    assert "onPluginValueChange?.(versionKey, null)" in option_source
    assert "workflowIdForVersionOption(option?.key, pluginValues)" in option_source
    assert "workflowApi\n      .versions(workflowId)" in option_source
    assert "WorkflowIoContractResponse" in option_source
    assert "versionIdForWorkflowOption(option?.key, pluginValues)" in option_source
    assert "workflowApi\n      .ioContract(stringValue, selectedVersionId)" in option_source
    assert "workflowCallableInterfaceLabels(ioContract?.interface)" in option_source
    assert "workflowSchemaFieldLabels(ioContract?.input_schema, { nested: true, limit: 4 })" in option_source
    assert "workflowSchemaFieldLabels(ioContract?.output_schema, { nested: true, limit: 4 })" in option_source
    assert "export function workflowCallableInterfaceLabels" in contract_source
    assert "workflowInterfaceToolField(entry.tool, entry.argument) || \"workflow_run.input\"" in contract_source
    assert "workflowInterfaceToolField(exit.schema_tool, exit.schema_field) || \"workflow_get_schema.output_schema\"" in contract_source
    assert 't("workflowPlugin.selector.interface")' in option_source
    assert 't("workflowPlugin.selector.entry")' in option_source
    assert 't("workflowPlugin.selector.exit")' in option_source
    assert "export function workflowSchemaFieldLabels" in contract_source
    assert 'prefix: `${fieldPath}[]`' in contract_source
    assert 't("workflowPlugin.selector.inputs")' in option_source
    assert 't("workflowPlugin.selector.outputs")' in option_source
    assert 't("workflowPlugin.selector.selectWorkflowFirst")' in option_source
    assert "export async function resolveWorkflowPluginVersionLabels" in option_source
    assert "onPluginValueChange" in project_renderer_source
    assert '"workflow.WorkflowVersionSelectOption"' in project_renderer_source
    assert "onPluginValueChange" in scheduled_renderer_source
    assert '"workflow.WorkflowVersionSelectOption"' in scheduled_renderer_source
    assert "resolveWorkflowPluginVersionLabels" in scheduled_renderer_source


def test_workflow_scheduled_task_input_option_uses_io_contract() -> None:
    option_source = (
        REPO_ROOT / "frontend" / "src" / "plugins" / "workflow" / "WorkflowSelectOption.tsx"
    ).read_text(encoding="utf-8")
    contract_source = CONTRACT_UTILS_SOURCE.read_text(encoding="utf-8")
    scheduled_renderer_source = (
        REPO_ROOT
        / "frontend"
        / "src"
        / "components"
        / "panels"
        / "ScheduledTaskPanel"
        / "scheduledTaskOptionRenderers.tsx"
    ).read_text(encoding="utf-8")
    builtin_source = (
        REPO_ROOT / "src" / "kernel" / "extensions" / "builtin_plugins.py"
    ).read_text(encoding="utf-8")
    package_frontend_source = (
        REPO_ROOT / "plugins" / "system" / "workflow" / "frontend" / "plugin.json"
    ).read_text(encoding="utf-8")

    assert "export function WorkflowPluginInputOption" in option_source
    assert "SELECTED_WORKFLOW_INPUT_JSON: \"SELECTED_WORKFLOW_ID\"" in option_source
    assert "SELECTED_WORKFLOW_INPUT_JSON: \"SELECTED_WORKFLOW_VERSION_ID\"" in option_source
    assert "workflowInputOptionWorkflowId(option?.key, pluginValues)" in option_source
    assert "workflowInputOptionVersionId(option?.key, pluginValues)" in option_source
    assert "workflowApi\n      .ioContract(workflowId, versionId)" in option_source
    assert 'sampleInputFromContract(ioContract, t("workflowPlugin.selector.sampleScheduledTask"))' in option_source
    assert 'from "./contractUtils"' in option_source
    assert "sampleWorkflowInputFromSchema" in option_source
    assert "workflowCallableInterfaceLabels" in option_source
    assert "workflowInputDraftStatus" in option_source
    assert "workflowSchemaFieldLabels(ioContract?.input_schema, { nested: true, limit: 4 })" in option_source
    assert "workflowSchemaFieldLabels(ioContract?.output_schema, { nested: true, limit: 4 })" in option_source
    assert "inputDraftError" in option_source
    assert "export function workflowInputDraftStatus" in contract_source
    assert "Missing required input:" in contract_source
    assert "export function workflowInputSchemaError" in contract_source
    assert "export function workflowInputExpectedTypes" in contract_source
    assert "schemaPath(path, field)" in contract_source
    assert "`${fieldPath}[${index}]`" in contract_source
    assert "Input type mismatch:" in contract_source
    assert "Input option mismatch:" in contract_source
    assert "Input must be a JSON object" in contract_source
    assert 't("workflowPlugin.selector.fillFromContract")' in option_source
    assert 't("workflowPlugin.selector.interface")' in option_source
    assert 't("workflowPlugin.selector.entry")' in option_source
    assert 't("workflowPlugin.selector.exit")' in option_source
    assert 't("workflowPlugin.selector.outputs")' in option_source
    assert "WorkflowPluginInputOption" in scheduled_renderer_source
    assert '"workflow.WorkflowInputOption"' in scheduled_renderer_source
    assert '"WORKFLOW_INPUT_JSON"' in builtin_source
    assert '"renderer": "workflow.WorkflowInputOption"' in package_frontend_source


def test_scheduled_task_history_surfaces_workflow_results() -> None:
    session_list_source = (
        REPO_ROOT
        / "frontend"
        / "src"
        / "components"
        / "panels"
        / "ScheduledTaskPanel"
        / "TaskSessionList.tsx"
    ).read_text(encoding="utf-8")

    assert "scheduledTaskApi.getRuns(taskId, WORKFLOW_RUN_HISTORY_LIMIT, 0)" in session_list_source
    assert "workflowResultFromRun" in session_list_source
    assert "output.workflow_result" in session_list_source
    assert "pluginResults?.workflow" in session_list_source
    assert "workflowRunsFromRuns(runResponse.items)" in session_list_source
    assert 't("scheduledTask.workflowResults", "Workflow results")' in session_list_source
    assert "workflowResultPreview(workflowResult)" in session_list_source
    assert "function workflowResultOutputEntries" in session_list_source
    assert "workflowOutputPathValue" in session_list_source
    assert "workflowSchemaFieldDescriptors" in session_list_source
    assert "workflowCallableInterfaceLabels" in session_list_source
    assert "function workflowResultOutputSchema" in session_list_source
    assert "workflowResultOutputSchema(result)" in session_list_source
    assert "workflowResultOutputFieldPaths(result)" in session_list_source
    assert "workflowOutputPathValue(output ?? {}, field)" in session_list_source
    assert "workflowOutputPathValue(output, key)" in session_list_source
    assert 'const keys = [' in session_list_source
    assert '"answer",' in session_list_source
    assert "const outputEntries = workflowResultOutputEntries(workflowResult)" in session_list_source
    assert "outputEntries.length > 0" in session_list_source
    assert "title={`${entry.key}: ${entry.value}`}" in session_list_source
    assert "function workflowResultInterfaceEntries" in session_list_source
    assert "const labels = workflowCallableInterfaceLabels(interfacePayload)" in session_list_source
    assert 'key: "Entry"' in session_list_source
    assert "value: labels.entry" in session_list_source
    assert "title: labels.entrySchema" in session_list_source
    assert 'key: "Exit"' in session_list_source
    assert "value: labels.exit" in session_list_source
    assert "title: labels.exitSchema" in session_list_source
    assert "const interfaceEntries = workflowResultInterfaceEntries(workflowResult)" in session_list_source
    assert "interfaceEntries.length > 0" in session_list_source
    assert 't("scheduledTask.workflowInterface", "Interface")' in session_list_source
    assert "function workflowNextActionEntries" in session_list_source
    assert "const approval = asRecord(action.approval)" in session_list_source
    assert "const pending = asRecord(action.pending)" in session_list_source
    assert "const resume = asRecord(action.resume)" in session_list_source
    assert '{ key: "approval", value: approval?.title || approval?.node_id }' in session_list_source
    assert '{ key: "resume", value: resume?.tool }' in session_list_source
    assert '{ key: "resume_path", value: resume?.path }' in session_list_source
    assert '{ key: "pending", value: pending?.path }' in session_list_source
    assert "const nextActionEntries = workflowNextActionEntries(workflowResult)" in session_list_source
    assert "nextActionEntries.length > 0" in session_list_source
    assert 't("scheduledTask.workflowNextAction", "Next action")' in session_list_source
    assert "`/workflows/${encodeURIComponent(workflowId)}/runs/${encodeURIComponent(workflowRunId)}`" in session_list_source
    assert "<RunStatusBadge status={run.status} />" in session_list_source


def test_chat_workflow_picker_can_pin_selected_workflow_version() -> None:
    picker_source = (
        REPO_ROOT / "frontend" / "src" / "plugins" / "workflow" / "WorkflowPickerModal.tsx"
    ).read_text(encoding="utf-8")
    panel_renderer_source = (
        REPO_ROOT / "frontend" / "src" / "components" / "chat" / "chatInputPanelRenderers.tsx"
    ).read_text(encoding="utf-8")
    selected_renderer_source = (
        REPO_ROOT / "frontend" / "src" / "components" / "chat" / "chatInputSelectedRenderers.tsx"
    ).read_text(encoding="utf-8")

    assert "selectedVersionId?: string | null" in picker_source
    assert "onSelectVersion?: (versionId: string | null) => void" in picker_source
    assert "const [versions, setVersions] = useState<WorkflowVersionSummary[]>([])" in picker_source
    assert "const [ioContract, setIoContract] = useState<WorkflowIoContractResponse | null>(null)" in picker_source
    assert "workflowApi\n      .versions(selectedWorkflowId)" in picker_source
    assert "workflowApi\n      .ioContract(selectedWorkflowId, selectedVersionId ?? null)" in picker_source
    assert "workflowSchemaFieldLabels(ioContract?.input_schema, { nested: true, limit: 6 })" in picker_source
    assert "workflowSchemaFieldLabels(ioContract?.output_schema, { nested: true, limit: 6 })" in picker_source
    assert 't("workflowPlugin.picker.usePublishedOrLatest")' in picker_source
    assert 't("workflowPlugin.selector.inputs")' in picker_source
    assert 't("workflowPlugin.selector.outputs")' in picker_source
    assert "onSelectVersion(nextValue || null)" in picker_source
    assert "WORKFLOW_PLUGIN_SESSION_VERSION_KEY" in panel_renderer_source
    assert "selectedVersionId={effectiveSelectedVersionId}" in panel_renderer_source
    assert "onSelectVersion={handleSelectVersion}" in panel_renderer_source
    assert "onPluginOptionChange?.(optionPath.pluginId, WORKFLOW_PLUGIN_SESSION_VERSION_KEY, null)" in panel_renderer_source
    assert "type WorkflowVersionSummary" in selected_renderer_source
    assert "workflowApi\n      .versions(effectiveSelectedWorkflowId)" in selected_renderer_source
    assert "const versionLabel = effectiveSelectedVersionId" in selected_renderer_source
    assert "`${workflowLabel} / ${versionLabel}`" in selected_renderer_source


def test_workflow_panel_surfaces_callable_entry_exit_contract_before_run() -> None:
    source = PANEL_SOURCE.read_text(encoding="utf-8")
    api_source = (
        REPO_ROOT / "frontend" / "src" / "plugins" / "workflow" / "api.ts"
    ).read_text(encoding="utf-8")

    assert "function workflowContractInterfaceItems" in source
    assert "workflow: WorkflowSummary | null" in source
    assert "contract: WorkflowIoContractResponse | null" in source
    assert "const interfacePayload = workflowInterfaceObject(contract?.interface)" in source
    assert "const entry = workflowInterfaceObject(interfacePayload.entry)" in source
    assert "const exit = workflowInterfaceObject(interfacePayload.exit)" in source
    assert "const schema = workflowInterfaceObject(interfacePayload.schema)" in source
    assert "const entryValue = workflowInterfaceToolField(entry.tool, entry.argument)" in source
    assert "const exitValue = workflowInterfaceText(exit.field)" in source
    assert "const schemaValue = workflowInterfaceText(schema.tool)" in source
    assert "schema?: {" in api_source
    assert "run?: {" in api_source
    assert "run_id_field?: string;" in api_source
    assert "interface?: WorkflowRunInterface | null;" in api_source
    assert api_source.count("interface?: WorkflowRunInterface | null;") >= 4
    assert 'label: "Entry"' in source
    assert 'value: entryValue || "workflow_run.input"' in source
    assert "workflowInterfaceToolField(entry.schema_tool, entry.schema_field) || contract?.input_schema_source || \"input_schema\"" in source
    assert 'label: "Exit"' in source
    assert 'value: exitValue || "output"' in source
    assert "workflowInterfaceToolField(exit.schema_tool, exit.schema_field) || contract?.output_schema_source || \"output_schema\"" in source
    assert 'label: "Schema"' in source
    assert 'value: schemaValue || "workflow_get_schema"' in source
    assert "workflowInterfaceText(schema.version_id) || versionDetail" in source
    assert "const contractInterfaceItems = useMemo" in source
    assert "workflowContractInterfaceItems(selectedWorkflow, ioContract)" in source
    assert 'data-testid="workflow-interface-contract"' in source
    assert 'data-testid={`workflow-interface-${item.label.toLowerCase()}`}' in source
    assert 't("workflowPlugin.editor.run.workflowInterface")' in source
    assert 't("workflowPlugin.plugin.name")' in source

    input_form_index = source.index("<WorkflowInputForm")
    interface_index = source.index('data-testid="workflow-interface-contract"', input_form_index)
    output_contract_index = source.index('t("workflowPlugin.editor.run.outputContract")', interface_index)
    run_button_index = source.index('data-testid="workflow-run-version"', output_contract_index)
    assert input_form_index < interface_index < output_contract_index < run_button_index
