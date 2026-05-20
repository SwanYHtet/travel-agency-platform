<script setup>
import { ref, reactive } from 'vue'
import { recommendationsService } from '../services/recommendationsService.js'

const today = new Date().toISOString().split('T')[0]
// Must match the cities that Phase 2 has flight and hotel data for.
const SUPPORTED_CITIES = ['Tokyo', 'Seoul', 'Paris', 'London', 'New York', 'Los Angeles', 'San Francisco']
// Tags correspond to the tag values in the Phase 2 hotel list; the empty string means no filter.
const HOTEL_TAGS = ['', 'luxury', 'modern', 'scenic', 'budget']

const form = reactive({
  city: 'Tokyo',
  origin: 'SFO',
  departureDate: '',
  budget: 2000,
  minRating: 0,
  maxHotelPrice: '',
  tag: '',
})

const isLoading = ref(false)
const errorMessage = ref('')
const result = ref(null)
const hasSearched = ref(false)

async function handleSearch() {
  errorMessage.value = ''
  result.value = null

  if (!form.city) { errorMessage.value = 'Please select a destination city.'; return }
  if (!form.departureDate) { errorMessage.value = 'Departure date is required.'; return }
  if (!form.budget || form.budget <= 0) { errorMessage.value = 'Budget must be greater than 0.'; return }

  isLoading.value = true
  hasSearched.value = true

  try {
    result.value = await recommendationsService.search({
      city: form.city,
      budget: form.budget,
      origin: form.origin,
      departureDate: form.departureDate,
      minRating: form.minRating,
      maxHotelPrice: form.maxHotelPrice || null,
      tag: form.tag || null,
    })

    if (!result.value?.top3Packages?.length) {
      errorMessage.value = result.value?.message || 'No packages found within your budget. Try increasing it or adjusting filters.'
    }
  } catch (err) {
    errorMessage.value = err?.response?.data?.detail || err.message || 'Recommendation search failed. Make sure the Phase 2 backend is running on port 8001.'
  } finally {
    isLoading.value = false
  }
}

function formatCost(val) {
  return `$${Number(val || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}
</script>

<template>
  <div class="rec-view">
    <!-- Search bar -->
    <div class="rec-search">
      <div class="rec-search__inner">
        <h2 class="rec-search__title">Trip Recommendations</h2>
        <p class="rec-search__sub">Enter a destination and budget — we'll find the best flight + hotel combos for you.</p>

        <div class="rec-form">
          <div class="rec-form__row">
            <div class="rec-field">
              <label class="rec-field__label">Destination City</label>
              <select v-model="form.city" class="rec-field__input">
                <option v-for="c in SUPPORTED_CITIES" :key="c" :value="c">{{ c }}</option>
              </select>
            </div>
            <div class="rec-field rec-field--narrow">
              <label class="rec-field__label">From (IATA)</label>
              <input v-model="form.origin" class="rec-field__input" placeholder="SFO" maxlength="3" />
            </div>
            <div class="rec-field">
              <label class="rec-field__label">Departure Date</label>
              <input v-model="form.departureDate" class="rec-field__input" type="date" :min="today" />
            </div>
            <div class="rec-field">
              <label class="rec-field__label">Total Budget ($)</label>
              <input v-model.number="form.budget" class="rec-field__input" type="number" min="1" placeholder="2000" />
            </div>
            <div class="rec-field rec-field--narrow">
              <label class="rec-field__label">Min Rating</label>
              <input v-model.number="form.minRating" class="rec-field__input" type="number" min="0" max="5" step="0.1" />
            </div>
            <div class="rec-field rec-field--narrow">
              <label class="rec-field__label">Max Hotel/Night</label>
              <input v-model="form.maxHotelPrice" class="rec-field__input" type="number" min="0" placeholder="Any" />
            </div>
            <div class="rec-field rec-field--narrow">
              <label class="rec-field__label">Hotel Tag</label>
              <select v-model="form.tag" class="rec-field__input">
                <option value="">Any</option>
                <option v-for="t in HOTEL_TAGS.slice(1)" :key="t" :value="t">{{ t }}</option>
              </select>
            </div>
            <div class="rec-field rec-field--action">
              <label class="rec-field__label">&nbsp;</label>
              <button class="rec-btn-search" :disabled="isLoading" @click="handleSearch">
                <span v-if="isLoading" class="spinner" />
                <span v-else>Find Packages</span>
              </button>
            </div>
          </div>
          <p v-if="errorMessage" class="rec-error">{{ errorMessage }}</p>
        </div>
      </div>
    </div>

    <!-- Results -->
    <div class="rec-results">
      <div v-if="isLoading" class="rec-state">Searching best packages to {{ form.city }}...</div>

      <template v-else-if="result?.top3Packages?.length">
        <div class="rec-meta">
          {{ result.totalPackagesFound }} packages evaluated · showing top {{ result.top3Packages.length }}
          · preferred airline: {{ result.bestRecommendation?.flight?.legs?.[0]?.airline || '—' }}
        </div>

        <div class="rec-packages">
          <div
            v-for="(pkg, pi) in result.top3Packages"
            :key="pi"
            class="rec-package"
            :class="{ 'rec-package--best': pi === 0 }"
          >
            <div class="rec-package__header">
              <div>
                <span class="rec-package__rank">{{ pi === 0 ? 'Best Pick' : `Option ${pi + 1}` }}</span>
                <span class="rec-package__score">Score {{ pkg.recommendationScore }}</span>
              </div>
              <div class="rec-package__totals">
                <span class="rec-package__total">{{ formatCost(pkg.totalPackageCost) }}</span>
                <span class="rec-package__remaining">{{ formatCost(pkg.remainingBudget) }} under budget</span>
              </div>
            </div>

            <!-- Flight -->
            <section class="rec-section">
              <h3 class="rec-section__title">Flight</h3>
              <div v-for="(leg, li) in pkg.flight.legs" :key="li" class="rec-flight">
                <span class="rec-flight__route">{{ leg.from }} → {{ leg.to }}</span>
                <span class="rec-flight__info">{{ leg.airline }} {{ leg.flightNumber }} · {{ leg.departureTime }}</span>
                <span class="rec-flight__cost">{{ formatCost(pkg.flight.totalCost) }}</span>
              </div>
            </section>

            <!-- Hotel -->
            <section class="rec-section">
              <h3 class="rec-section__title">Hotel</h3>
              <div class="rec-hotel">
                <div class="rec-hotel__name">{{ pkg.hotel.name }}</div>
                <div class="rec-hotel__meta">
                  Rating {{ pkg.hotel.rating }} · {{ pkg.hotel.nights }} nights ·
                  ${{ pkg.hotel.pricePerNight }}/night · {{ formatCost(pkg.hotel.totalStayCost) }}
                  <span v-if="pkg.hotel.featuredForTenant" class="rec-featured">Featured</span>
                </div>
              </div>
            </section>

            <!-- Attractions -->
            <section v-if="pkg.suggestedAttractions?.length" class="rec-section">
              <h3 class="rec-section__title">Top Activities</h3>
              <div class="rec-attractions">
                <span v-for="a in pkg.suggestedAttractions" :key="a.name" class="rec-attraction-tag">
                  {{ a.name }}
                  <span v-if="a.price > 0"> · ${{ a.price }}</span>
                  <span v-else> · Free</span>
                </span>
              </div>
            </section>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.rec-view { min-height: calc(100vh - 56px); background: var(--color-bg); }

.rec-search {
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-dark) 100%);
  padding: 1.5rem 2rem;
  box-shadow: 0 4px 20px rgba(0,0,0,0.15);
}
.rec-search__inner { max-width: 1200px; margin: 0 auto; }
.rec-search__title { margin: 0 0 0.15rem; color: #fff; font-size: 1.25rem; font-weight: 800; }
.rec-search__sub { margin: 0 0 1rem; color: rgba(255,255,255,0.75); font-size: 0.85rem; }

.rec-form__row { display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: flex-end; }
.rec-field { display: flex; flex-direction: column; gap: 0.3rem; flex: 1; min-width: 120px; }
.rec-field--narrow { flex: 0 0 100px; }
.rec-field--action { flex: 0 0 auto; }
.rec-field__label { font-size: 0.7rem; font-weight: 600; color: rgba(255,255,255,0.8); text-transform: uppercase; letter-spacing: 0.05em; }
.rec-field__input {
  height: 40px; padding: 0 0.75rem;
  border: 1.5px solid rgba(255,255,255,0.3); border-radius: 8px;
  background: rgba(255,255,255,0.12); color: #fff; font-size: 0.9rem;
  outline: none; box-sizing: border-box; width: 100%;
}
.rec-field__input option { color: #1a365d; background: #fff; }
.rec-field__input::placeholder { color: rgba(255,255,255,0.45); }
.rec-field__input:focus { border-color: rgba(255,255,255,0.7); background: rgba(255,255,255,0.2); }
.rec-field__input::-webkit-calendar-picker-indicator { filter: invert(1) opacity(0.7); cursor: pointer; }

.rec-btn-search {
  height: 40px; padding: 0 1.5rem;
  background: var(--color-accent); color: #fff; border: none;
  border-radius: 8px; font-size: 0.95rem; font-weight: 700;
  cursor: pointer; display: flex; align-items: center; gap: 0.4rem;
  white-space: nowrap; transition: background 0.2s;
}
.rec-btn-search:hover:not(:disabled) { background: var(--color-accent-dark); }
.rec-btn-search:disabled { opacity: 0.7; cursor: not-allowed; }
.rec-error { color: #ffcdd2; font-size: 0.85rem; margin: 0.5rem 0 0; }

.rec-results { max-width: 1200px; margin: 1.5rem auto; padding: 0 2rem; }
.rec-state { background: #fff; border: 1px solid var(--color-border); border-radius: 16px; padding: 2rem; color: var(--color-text-muted); text-align: center; }
.rec-meta { margin-bottom: 1rem; font-size: 0.85rem; color: var(--color-text-muted); }

.rec-packages { display: flex; flex-direction: column; gap: 1rem; }
.rec-package {
  background: #fff; border: 1px solid var(--color-border);
  border-radius: 18px; padding: 1.5rem;
  box-shadow: 0 8px 24px rgba(26,54,93,0.06);
}
.rec-package--best { border-color: var(--color-primary); border-width: 2px; }

.rec-package__header { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 1rem; flex-wrap: wrap; }
.rec-package__rank { font-size: 1rem; font-weight: 800; color: var(--color-primary-dark); }
.rec-package__score { margin-left: 0.75rem; font-size: 0.8rem; color: var(--color-text-muted); }
.rec-package__totals { display: flex; flex-direction: column; align-items: flex-end; gap: 0.1rem; }
.rec-package__total { font-size: 1.4rem; font-weight: 800; color: var(--color-primary-dark); }
.rec-package__remaining { font-size: 0.8rem; color: #16a34a; font-weight: 600; }

.rec-section { margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--color-border); }
.rec-section__title { margin: 0 0 0.6rem; font-size: 0.9rem; font-weight: 700; color: var(--color-text); }

.rec-flight { display: flex; align-items: center; gap: 1rem; padding: 0.5rem 0.75rem; background: #f8faff; border-radius: 8px; border: 1px solid var(--color-border); flex-wrap: wrap; }
.rec-flight__route { font-weight: 700; color: var(--color-primary-dark); min-width: 80px; }
.rec-flight__info { flex: 1; font-size: 0.88rem; color: var(--color-text-muted); }
.rec-flight__cost { font-weight: 700; }

.rec-hotel { padding: 0.75rem; background: #f8faff; border-radius: 10px; border: 1px solid var(--color-border); }
.rec-hotel__name { font-weight: 700; color: var(--color-primary-dark); margin-bottom: 0.25rem; }
.rec-hotel__meta { font-size: 0.85rem; color: var(--color-text-muted); }
.rec-featured { margin-left: 0.5rem; background: var(--color-accent); color: #fff; border-radius: 999px; padding: 0.1rem 0.5rem; font-size: 0.75rem; font-weight: 700; }

.rec-attractions { display: flex; flex-wrap: wrap; gap: 0.4rem; }
.rec-attraction-tag { background: var(--color-primary-bg); color: var(--color-primary-dark); border-radius: 999px; padding: 0.2rem 0.6rem; font-size: 0.78rem; font-weight: 600; }

.spinner { width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.4); border-top-color: #fff; border-radius: 50%; animation: spin 0.7s linear infinite; display: inline-block; }
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 768px) {
  .rec-search { padding: 1rem; }
  .rec-results { padding: 0 1rem; }
  .rec-package__header { flex-direction: column; }
  .rec-package__totals { align-items: flex-start; }
}
</style>
