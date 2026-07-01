<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div class="card">
      <div class="card-header">
        <h3 class="card-title">{{ t('restocking.budget') }}</h3>
      </div>
      <div class="budget-controls">
        <input
          type="range"
          min="1000"
          max="100000"
          step="1000"
          v-model.number="budget"
          class="budget-slider"
        />
        <div class="budget-value">${{ budget.toLocaleString() }}</div>
        <div class="budget-summary">
          <div>
            {{ t('restocking.selectedTotal') }}:
            <strong>${{ localTotal.toLocaleString() }}</strong>
          </div>
          <div :class="{ 'over-budget': overBudget }">
            {{ t('restocking.remaining') }}:
            <strong>${{ (budget - localTotal).toLocaleString() }}</strong>
          </div>
        </div>
      </div>
    </div>

    <div v-if="successMessage" class="success-banner">{{ successMessage }}</div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else class="card">
      <div class="card-header">
        <h3 class="card-title">
          {{ t('restocking.recommendations') }} ({{ recommendations.length }})
        </h3>
      </div>
      <div v-if="!recommendations.length" class="empty-state">
        {{ t('restocking.noRecommendations') }}
      </div>
      <template v-else>
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.select') }}</th>
                <th>{{ t('inventory.table.sku') }}</th>
                <th>{{ t('inventory.table.itemName') }}</th>
                <th>{{ t('inventory.table.warehouse') }}</th>
                <th>{{ t('demand.table.trend') }}</th>
                <th>{{ t('restocking.table.onHand') }}</th>
                <th>{{ t('restocking.table.forecast') }}</th>
                <th>{{ t('restocking.table.shortfall') }}</th>
                <th>{{ t('restocking.table.recommendedQty') }}</th>
                <th>{{ t('inventory.table.unitCost') }}</th>
                <th>{{ t('restocking.table.lineCost') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="rec in recommendations"
                :key="rec.item_sku"
                :class="{ dimmed: !rec.selected }"
              >
                <td>
                  <input type="checkbox" v-model="rec.selected" />
                </td>
                <td><strong>{{ rec.item_sku }}</strong></td>
                <td>{{ rec.item_name }}</td>
                <td>{{ rec.warehouse }}</td>
                <td>
                  <span :class="['badge', rec.trend]">
                    {{ t(`trends.${rec.trend}`) }}
                  </span>
                </td>
                <td>{{ rec.quantity_on_hand }}</td>
                <td>{{ rec.forecasted_demand }}</td>
                <td>{{ rec.shortfall }}</td>
                <td><strong>{{ rec.recommended_quantity }}</strong></td>
                <td>${{ rec.unit_cost.toFixed(2) }}</td>
                <td><strong>${{ rec.line_cost.toLocaleString() }}</strong></td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="order-footer">
          <div class="footer-total">
            {{ t('restocking.selectedTotal') }}:
            <strong>${{ localTotal.toLocaleString() }}</strong>
          </div>
          <button
            class="btn-primary"
            :disabled="submitting || !selectedItems.length || overBudget"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.placingOrder') : t('restocking.placeOrder') }}
          </button>
        </div>
      </template>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '../api'
import { useFilters } from '../composables/useFilters'
import { useI18n } from '../composables/useI18n'

export default {
  name: 'Restocking',
  setup() {
    const { t } = useI18n()
    const { selectedLocation, selectedCategory, getCurrentFilters } = useFilters()

    const loading = ref(true)
    const error = ref(null)
    const submitting = ref(false)
    const successMessage = ref(null)
    const budget = ref(25000)
    const recommendations = ref([])

    const selectedItems = computed(() => {
      return recommendations.value.filter(r => r.selected)
    })

    const localTotal = computed(() => {
      return selectedItems.value.reduce((sum, r) => sum + r.line_cost, 0)
    })

    const overBudget = computed(() => {
      return localTotal.value > budget.value
    })

    const loadRecommendations = async () => {
      try {
        loading.value = true
        error.value = null
        successMessage.value = null
        const data = await api.getRestockingRecommendations(budget.value, getCurrentFilters())
        recommendations.value = data.recommendations
      } catch (err) {
        error.value = 'Failed to load restocking recommendations: ' + err.message
      } finally {
        loading.value = false
      }
    }

    const placeOrder = async () => {
      try {
        submitting.value = true
        const items = selectedItems.value.map(r => ({
          sku: r.item_sku,
          quantity: r.recommended_quantity
        }))
        await api.createPurchaseOrder(items)
        successMessage.value = t('restocking.orderPlaced', { count: items.length })
        await loadRecommendations()
      } catch (err) {
        error.value = 'Failed to place order: ' + err.message
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadRecommendations)

    watch([budget, selectedLocation, selectedCategory], loadRecommendations)

    return {
      t,
      loading,
      error,
      submitting,
      successMessage,
      budget,
      recommendations,
      selectedItems,
      localTotal,
      overBudget,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-controls {
  padding: 20px;
}

.budget-slider {
  width: 100%;
  accent-color: #2563eb;
}

.budget-value {
  font-size: 28px;
  font-weight: 700;
  color: #0f172a;
  margin-top: 12px;
}

.budget-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 24px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #e2e8f0;
  font-size: 14px;
  color: #475569;
}

.budget-summary strong {
  color: #0f172a;
}

.over-budget,
.over-budget strong {
  color: #dc2626;
}

.success-banner {
  background: #d1fae5;
  color: #065f46;
  padding: 12px 16px;
  border-radius: 6px;
  margin-bottom: 20px;
  font-weight: 500;
}

.empty-state {
  padding: 40px 20px;
  text-align: center;
  color: #64748b;
}

.dimmed {
  opacity: 0.45;
}

.order-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-top: 1px solid #e2e8f0;
}

.footer-total {
  font-size: 15px;
  color: #475569;
}

.footer-total strong {
  color: #0f172a;
  font-size: 16px;
}

.btn-primary {
  background: #2563eb;
  color: white;
  padding: 10px 20px;
  border-radius: 6px;
  font-weight: 600;
  border: none;
  cursor: pointer;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary:hover:not(:disabled) {
  background: #1d4ed8;
}
</style>
