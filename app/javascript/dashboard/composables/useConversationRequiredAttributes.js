import { computed } from 'vue';
import { useMapGetter } from 'dashboard/composables/store';
import { useAccount } from 'dashboard/composables/useAccount';
import { FEATURE_FLAGS } from 'dashboard/featureFlags';
import { ATTRIBUTE_TYPES } from 'dashboard/components-next/ConversationWorkflow/constants';
import { getMissingRequiredFields } from 'dashboard/servicedesk/ticketFormHelper';

/**
 * Composable for managing conversation required attributes workflow
 *
 * This handles the logic for checking if conversations have all required
 * custom attributes filled before they can be resolved.
 */
export function useConversationRequiredAttributes() {
  const { currentAccount, accountId } = useAccount();
  const isFeatureEnabledonAccount = useMapGetter(
    'accounts/isFeatureEnabledonAccount'
  );
  const conversationAttributes = useMapGetter(
    'attributes/getConversationAttributes'
  );
  const attributesByModel = useMapGetter('attributes/getAttributesByModel');

  // ServiceDesk (M1): campos obrigatórios do formulário do ticket ao resolver
  // (servicedesk_require_form_on_resolve da conta, desligado por padrão)
  const isFormRequiredOnResolve = computed(
    () => currentAccount.value?.servicedesk?.require_form_on_resolve === true
  );

  const isFeatureEnabled = computed(() =>
    isFeatureEnabledonAccount.value(
      accountId.value,
      FEATURE_FLAGS.CONVERSATION_REQUIRED_ATTRIBUTES
    )
  );

  const requiredAttributeKeys = computed(() => {
    if (!isFeatureEnabled.value) return [];
    return (
      currentAccount.value?.settings?.conversation_required_attributes || []
    );
  });

  const allAttributeOptions = computed(() =>
    (conversationAttributes.value || []).map(attribute => ({
      ...attribute,
      value: attribute.attributeKey,
      label: attribute.attributeDisplayName,
      type: attribute.attributeDisplayType,
      attributeValues: attribute.attributeValues,
    }))
  );

  /**
   * Get the full attribute definitions for only the required attributes
   * Filters allAttributeOptions to only include attributes marked as required
   */
  const requiredAttributes = computed(
    () =>
      requiredAttributeKeys.value
        .map(key =>
          allAttributeOptions.value.find(attribute => attribute.value === key)
        )
        .filter(Boolean) // Remove any undefined attributes (deleted attributes)
  );

  const missingFormAttributes = (values = {}) => {
    if (!isFormRequiredOnResolve.value) return [];
    const definitions = attributesByModel.value('conversation_attribute') || [];
    const options = allAttributeOptions.value;
    return getMissingRequiredFields({ attributes: definitions, values })
      .map(field => options.find(option => option.value === field.key))
      .filter(Boolean);
  };

  /**
   * Check if a conversation is missing any required attributes
   *
   * @param {Object} conversationCustomAttributes - Current conversation's custom attributes
   * @returns {Object} - Analysis result with missing attributes info
   */
  const checkMissingAttributes = (conversationCustomAttributes = {}) => {
    const formMissing = missingFormAttributes(conversationCustomAttributes);

    // If no attributes are required, conversation can be resolved
    if (!requiredAttributes.value.length) {
      return formMissing.length
        ? { hasMissing: true, missing: formMissing, all: formMissing }
        : { hasMissing: false, missing: [] };
    }

    // Find attributes that are missing or empty
    const nativeMissing = requiredAttributes.value.filter(attribute => {
      const value = conversationCustomAttributes[attribute.value];

      // A checkbox is filled once true or false is picked. An explicit null is
      // an unanswered prompt, which is how the modal and the backend read it.
      if (attribute.type === ATTRIBUTE_TYPES.CHECKBOX) {
        return value == null;
      }

      // For other attribute types, only consider null, undefined, empty string, or whitespace-only as missing
      // Allow falsy values like 0, false as they are valid filled values
      return value == null || String(value).trim() === '';
    });
    const nativeKeys = new Set(nativeMissing.map(attribute => attribute.value));
    const missing = [
      ...nativeMissing,
      ...formMissing.filter(attribute => !nativeKeys.has(attribute.value)),
    ];

    return {
      hasMissing: missing.length > 0,
      missing,
      all: requiredAttributes.value,
    };
  };

  return {
    requiredAttributeKeys,
    requiredAttributes,
    checkMissingAttributes,
  };
}
