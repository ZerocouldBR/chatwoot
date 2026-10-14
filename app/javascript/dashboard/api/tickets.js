/* global axios */
import ApiClient from './ApiClient';

// Ticket actions that are not plain conversation updates: merge, spam and redaction.
class TicketsAPI extends ApiClient {
  constructor() {
    super('conversations', { accountScoped: true });
  }

  merge(id, { targetId, sourceComment, targetComment, isPublic }) {
    return axios.post(`${this.url}/${id}/merge`, {
      target_id: targetId,
      source_comment: sourceComment,
      target_comment: targetComment,
      public: isPublic,
    });
  }

  markAsSpam(id) {
    return axios.post(`${this.url}/${id}/spam`);
  }

  redact(id, messageId, { text, attachmentIds }) {
    return axios.post(`${this.url}/${id}/messages/${messageId}/redaction`, {
      text,
      attachment_ids: attachmentIds,
    });
  }
}

export default new TicketsAPI();
