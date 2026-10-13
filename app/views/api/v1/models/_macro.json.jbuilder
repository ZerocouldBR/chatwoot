json.id macro.id
json.name macro.name
json.visibility macro.visibility

if macro.created_by.present?
  json.created_by do
    json.partial! 'api/v1/models/agent', formats: [:json], resource: macro.created_by
  end
end

if macro.updated_by.present?
  json.updated_by do
    json.partial! 'api/v1/models/agent', formats: [:json], resource: macro.updated_by
  end
end

json.account_id macro.account_id
json.actions macro.actions
# ServiceDesk M5.1: resposta e nota da macro vão para o editor (o agente revisa e envia); ver Macros::ExecutionService
json.fill_editor macro.account.macro_fill_editor?
json.files macro.file_base_data if macro.files.any?
