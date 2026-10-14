class Api::V1::ProfilesController < Api::BaseController
  include MfaEnforcementGuard

  SD_LOCKED_PROFILE_FIELDS = %w[name display_name message_signature avatar].freeze # ServiceDesk M13

  before_action :set_user
  # show leaks pubsub_token, which grants realtime access; the rest of the
  # profile surface is equally off-limits to a token that MFA enforcement blocks.
  before_action :check_user_mfa_enforcement, if: :authenticate_by_access_token?

  def show; end

  def update
    if password_params[:password].present?
      render_could_not_create_error('Invalid current password') and return unless @user.valid_password?(password_params[:current_password])

      @user.update!(password_params.except(:current_password))
    end

    return render_sd_profile_locked if sd_profile_locked_change?

    @user.assign_attributes(profile_params)
    @user.custom_attributes.merge!(custom_attributes_params)
    @user.save!
  end

  def avatar
    return render_sd_profile_locked if sd_profile_locked?

    @user.avatar.attachment.destroy! if @user.avatar.attached?
    @user.reload
  end

  def auto_offline
    @user.account_users.find_by!(account_id: auto_offline_params[:account_id]).update!(auto_offline: auto_offline_params[:auto_offline] || false)
  end

  def availability
    @user.account_users.find_by!(account_id: availability_params[:account_id]).update!(availability: availability_params[:availability])
  end

  def set_active_account
    @user.account_users.find_by(account_id: profile_params[:account_id]).update(active_at: Time.now.utc)
    head :ok
  end

  def resend_confirmation
    @user.send_confirmation_instructions unless @user.confirmed?
    head :ok
  end

  def reset_access_token
    @user.access_token.regenerate_token
    @user.reload
  end

  private

  # ServiceDesk M13: papel sem profile.edit_own (Agente light e Colaborador no Zendesk) não altera nome, alias,
  # assinatura nem foto. Senha, idioma (ui_settings) e disponibilidade continuam liberados.
  def sd_profile_locked?
    @user.account_users.includes(:sd_role).any? { |account_user| !account_user.sd_access.can?('profile.edit_own') }
  end

  def sd_profile_locked_change?
    return false unless params[:profile].respond_to?(:key?)

    changed = SD_LOCKED_PROFILE_FIELDS.select { |field| params[:profile].key?(field) }
    changed = changed.reject { |field| field != 'avatar' && params[:profile][field].to_s == @user.public_send(field).to_s }
    changed.any? && sd_profile_locked?
  end

  def render_sd_profile_locked
    render json: { error: 'ServiceDesk: seu papel não permite alterar nome, alias, assinatura ou foto' }, status: :forbidden
  end

  def set_user
    @user = current_user
  end

  def availability_params
    params.require(:profile).permit(:account_id, :availability)
  end

  def auto_offline_params
    params.require(:profile).permit(:account_id, :auto_offline)
  end

  def profile_params
    params.require(:profile).permit(
      :email,
      :name,
      :display_name,
      :avatar,
      :message_signature,
      :account_id,
      ui_settings: {}
    )
  end

  def custom_attributes_params
    params.require(:profile).permit(:phone_number)
  end

  def password_params
    params.require(:profile).permit(
      :current_password,
      :password,
      :password_confirmation
    )
  end
end
