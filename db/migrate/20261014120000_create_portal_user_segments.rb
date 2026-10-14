# ServiceDesk B2B: segmentos de usuário da Central de Ajuda (equivalente a hc_user_segments do Zendesk Guide).
# Um artigo com portal_user_segment_id só aparece no portal para o contato logado que atende ao segmento.
class CreatePortalUserSegments < ActiveRecord::Migration[7.1]
  def change
    create_table :portal_user_segments do |t|
      t.references :account, null: false, index: true
      t.references :portal, null: false, index: true
      t.string :name, null: false
      # 0 = usuários conectados (contatos logados), 1 = equipe (nunca aparece no portal)
      t.integer :user_type, null: false, default: 0
      t.bigint :company_ids, array: true, null: false, default: []
      t.string :tags, array: true, null: false, default: []
      t.string :or_tags, array: true, null: false, default: []
      t.bigint :contact_ids, array: true, null: false, default: []
      t.string :external_id
      t.timestamps
    end
    add_index :portal_user_segments, [:portal_id, :external_id], unique: true, where: 'external_id IS NOT NULL'

    add_reference :articles, :portal_user_segment, index: true, null: true
  end
end
