# ServiceDesk (M7): histórico de alterações do ticket (status, responsável, time, prioridade, etiquetas e campos),
# no formato dos audits do Zendesk. Lido pela API de compatibilidade (/api/v2/tickets/:id/audits) que os
# workflows do n8n usam para saber quem atribuiu/comentou e quando.
class CreateSdTicketAudits < ActiveRecord::Migration[7.1]
  def change
    create_table :sd_ticket_audits do |t|
      t.references :account, null: false, index: false
      t.references :conversation, null: false, index: false
      t.string :author_type
      t.bigint :author_id
      t.string :via, null: false, default: 'web'
      # [{ "type": "Change", "field_name": "assignee_id", "value": "123", "previous_value": null }, ...]
      t.jsonb :events, null: false, default: []
      t.datetime :created_at, null: false
    end
    add_index :sd_ticket_audits, [:conversation_id, :id]
    add_index :sd_ticket_audits, :account_id
  end
end
