class Api::V1::Accounts::CustomAttributeDefinitionsController < Api::V1::Accounts::BaseController
  before_action :fetch_custom_attributes_definitions, except: [:create]
  before_action :fetch_custom_attribute_definition, only: [:show, :update, :destroy]
  before_action :check_authorization
  DEFAULT_ATTRIBUTE_MODEL = 'conversation_attribute'.freeze

  def index; end

  def show; end

  def create
    @custom_attribute_definition = Current.account.custom_attribute_definitions.create!(
      permitted_payload
    )
    show_in_ticket_panel if @custom_attribute_definition.conversation_attribute?
  end

  def update
    @custom_attribute_definition.update!(permitted_payload)
  end

  def destroy
    @custom_attribute_definition.destroy!
    head :no_content
  end

  private

  # A ticket field created by an admin shows up in the ticket's left column right away (Settings > Ticket fields hides it).
  def show_in_ticket_panel
    fields = Current.account.settings['ticket_panel_fields'] || Account::DEFAULT_TICKET_PANEL_FIELDS
    Current.account.settings['ticket_panel_fields'] = fields | ["attr:#{@custom_attribute_definition.attribute_key}"]
    Current.account.save!
  end

  def fetch_custom_attributes_definitions
    @custom_attribute_definitions = Current.account.custom_attribute_definitions.with_attribute_model(permitted_params[:attribute_model])
  end

  def fetch_custom_attribute_definition
    @custom_attribute_definition = Current.account.custom_attribute_definitions.find(permitted_params[:id])
  end

  def permitted_payload
    params.require(:custom_attribute_definition).permit(
      :attribute_display_name,
      :attribute_description,
      :attribute_display_type,
      :attribute_key,
      :attribute_model,
      :regex_pattern,
      :regex_cue,
      attribute_values: []
    )
  end

  def permitted_params
    params.permit(:id, :filter_type, :attribute_model)
  end
end
