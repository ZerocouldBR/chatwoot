class Avatar::AvatarFromGravatarJob < ApplicationJob
  queue_as :purgable

  def perform(avatarable, email)
    return if GlobalConfigService.load('DISABLE_GRAVATAR', '').present?
    return if email.blank?
    # ServiceDesk: conta isolada, o e-mail (hash) do contato não vai ao Gravatar.
    return if Servicedesk::OutboundGuard.blocked?(avatarable.try(:account))
    return if avatarable.avatar_url.present?

    hash = Digest::MD5.hexdigest(email)
    gravatar_url = "https://www.gravatar.com/avatar/#{hash}?d=404"
    Avatar::AvatarFromUrlJob.perform_later(avatarable, gravatar_url)
  end
end
