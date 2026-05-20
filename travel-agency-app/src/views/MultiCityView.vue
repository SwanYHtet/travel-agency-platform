<script setup>
import { ref, reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { multiCityService } from '../services/multiCityService.js'
import { tenantConfig } from '../config/tenantConfig.js'
import { useAuth } from '../composables/useAuth.js'

const router = useRouter()
const { userId } = useAuth()

const today = new Date().toISOString().split('T')[0]

// Phase 2 FLIGHT_DATA only has routes between these 7 cities.
// Any other city name will return a 400 from the backend's CITY_TO_IATA lookup.
const SUPPORTED_CITIES = ['Tokyo', 'Seoul', 'Paris', 'London', 'New York', 'Los Angeles', 'San Francisco']

const form = reactive({
  originIata: 'SFO',
  returnIata: 'SFO',
  departureDate: '',
  budget: 3000,
  nightsPerCity: 3,
  adults: 1,
  minRating: 0,
  maxHotelPricePerNight: '',
})

const cities = ref(['Tokyo', 'Seoul'])
const cityInput = ref('')
const cityError = ref('')

const computedReturnDate = computed(() => {
  if (!form.departureDate || cities.value.length === 0) return '—'
  const d = new Date(form.departureDate)
  d.setDate(d.getDate() + cities.value.length * (form.nightsPerCity || 3))
  return d.toISOString().split('T')[0]
})

const isLoading = ref(false)
const errorMessage = ref('')
const packages = ref([])
const hasSearched = ref(false)

const bookingPkgIndex = ref(null)
const bookingError = ref('')

const ATTRACTION_STORAGE_KEY = 'booking_attractions'

function saveBookingAttractions(bookingId, cityBreakdown) {
  try {
    const stored = JSON.parse(localStorage.getItem(ATTRACTION_STORAGE_KEY) || '{}')
    stored[bookingId] = cityBreakdown.map(entry => ({
      city: entry.city,
      attractionCost: entry.attractionCost,
      attractions: entry.suggestedAttractions,
    }))
    localStorage.setItem(ATTRACTION_STORAGE_KEY, JSON.stringify(stored))
  } catch {}
}

function addCity() {
  const val = cityInput.value.trim()
  if (!val) return
  const normalized = val.charAt(0).toUpperCase() + val.slice(1).toLowerCase()
  const supported = SUPPORTED_CITIES.find(c => c.toLowerCase() === normalized.toLowerCase())
  if (!supported) {
    cityError.value = `Supported cities: ${SUPPORTED_CITIES.join(', ')}`
    return
  }
  if (cities.value.includes(supported)) {
    cityError.value = `${supported} is already added.`
    return
  }
  cities.value.push(supported)
  cityInput.value = ''
  cityError.value = ''
}

function removeCity(index) {
  cities.value.splice(index, 1)
}

async function handleSearch() {
  errorMessage.value = ''
  cityError.value = ''

  if (cities.value.length < 1) {
    errorMessage.value = 'Add at least one destination city.'
    return
  }
  if (!form.departureDate) {
    errorMessage.value = 'Departure date is required.'
    return
  }
  if (!form.budget || form.budget <= 0) {
    errorMessage.value = 'Budget must be greater than 0.'
    return
  }

  isLoading.value = true
  hasSearched.value = true
  packages.value = []

  try {
    const result = await multiCityService.searchPackages({
      cities: cities.value,
      originIata: form.originIata,
      returnIata: form.returnIata,
      departureDate: form.departureDate,
      budget: form.budget,
      nightsPerCity: form.nightsPerCity,
      adults: form.adults,
      minRating: form.minRating,
      maxHotelPricePerNight: form.maxHotelPricePerNight || null,
    })

    packages.value = result.top3Packages || []

    if (packages.value.length === 0) {
      errorMessage.value = result.message || 'No packages found within your budget. Try increasing your budget.'
    }
  } catch (err) {
    errorMessage.value = err?.response?.data?.detail || err.message || 'Multi-city search failed. Make sure the Phase 2 backend is running on port 8001.'
  } finally {
    isLoading.value = false
  }
}

function formatCost(val) {
  return `$${Number(val || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

function parseFlightNumber(raw) {
  const match = String(raw || '').trim().toUpperCase().match(/^([A-Z]{2,3})(\d+[A-Z]?)$/)
  if (match) return { airlineCode: match[1], flightNumber: match[2] }
  return { airlineCode: 'XX', flightNumber: String(raw || '') }
}

function parseDateTime(dt) {
  // Phase 2 flight times are "YYYY-MM-DD HH:MM" — split into date and time parts.
  const parts = String(dt || '').split(' ')
  return { date: parts[0] || form.departureDate, time: parts[1] ? `${parts[1]}:00` : '00:00:00' }
}

async function bookPackage(pkg, pkgIndex) {
  bookingError.value = ''
  const uid = Number(userId.value)
  if (!uid || uid <= 0) {
    bookingError.value = 'Please sign in before booking.'
    return
  }

  bookingPkgIndex.value = pkgIndex

  // One reservation per flight leg in the package.
  const flightReservations = pkg.flightLegs.map(leg => {
    const legData = leg.flight.legs[0]
    const { airlineCode, flightNumber } = parseFlightNumber(legData.flightNumber)
    const dep = parseDateTime(legData.departureTime)
    const arr = parseDateTime(legData.arrivalTime)
    return {
      Airline_Code: airlineCode,
      Flight_Number: flightNumber,
      Departure_Date: dep.date,
      Departure_Time: dep.time,
      Arrive_Date: arr.date,
      Arrive_Time: arr.time,
      Rate: leg.flight.totalCost,
      Origin_Airport_Code: leg.origin,
      Destination_Airport_Code: leg.destination,
    }
  })

  // One reservation per city with correct check-in/out dates per city stay.
  const nightsPerCity = form.nightsPerCity || 3
  const hotelReservations = pkg.cityBreakdown
    .filter(entry => entry.hotel)
    .map((entry, idx) => {
      const checkIn = new Date(pkg.departureDate)
      checkIn.setDate(checkIn.getDate() + idx * nightsPerCity)
      const checkOut = new Date(checkIn)
      checkOut.setDate(checkOut.getDate() + nightsPerCity)
      const fmt = d => d.toISOString().split('T')[0]
      return {
        Hotel_Code: 0,
        Check_In_Date: fmt(checkIn),
        Check_In_Time: '15:00:00',
        Check_Out_Date: fmt(checkOut),
        Check_Out_Time: '11:00:00',
        Rate: entry.hotel.totalStayCost,
      }
    })

  try {
    const response = await axios.post('/api/v1/bookings/', {
      User_Id: uid,
      Agent_Id: tenantConfig.agentId,
      Start_Date: pkg.departureDate,
      End_Date: pkg.returnDate,
      hotel_reservations: hotelReservations,
      flight_reservations: flightReservations,
    })
    const bookingId = response.data?.Booking_Id ?? response.data?.booking_id ?? response.data?.id
    if (bookingId && pkg.cityBreakdown?.length) {
      saveBookingAttractions(bookingId, pkg.cityBreakdown)
    }
    router.push({ name: 'confirmation' })
  } catch (err) {
    bookingError.value = err?.response?.data?.detail || err.message || 'Booking failed.'
    bookingPkgIndex.value = null
  }
}
</script>

<template>
  <div class="mc-view">
    <!-- Search Form -->
    <div class="mc-search">
      <div class="mc-search__inner">
        <h2 class="mc-search__title">Multi-City Package Builder</h2>
        <p class="mc-search__sub">Build a complete trip: flights + hotels across multiple cities, within your budget.</p>

        <div class="mc-form">
          <!-- Row 1: Origin / Return / Date / Budget -->
          <div class="mc-form__row">
            <div class="mc-field">
              <label class="mc-field__label">Origin IATA</label>
              <input v-model="form.originIata" class="mc-field__input" placeholder="SFO" maxlength="3" />
            </div>
            <div class="mc-field">
              <label class="mc-field__label">Return IATA</label>
              <input v-model="form.returnIata" class="mc-field__input" placeholder="SFO" maxlength="3" />
            </div>
            <div class="mc-field">
              <label class="mc-field__label">Departure Date</label>
              <input v-model="form.departureDate" class="mc-field__input" type="date" :min="today" />
            </div>
            <div class="mc-field">
              <label class="mc-field__label">Return Date (computed)</label>
              <input class="mc-field__input mc-field__input--readonly" :value="computedReturnDate" readonly />
            </div>
            <div class="mc-field">
              <label class="mc-field__label">Total Budget ($)</label>
              <input v-model.number="form.budget" class="mc-field__input" type="number" min="1" placeholder="3000" />
            </div>
            <div class="mc-field mc-field--narrow">
              <label class="mc-field__label">Nights / City</label>
              <input v-model.number="form.nightsPerCity" class="mc-field__input" type="number" min="1" max="30" />
            </div>
            <div class="mc-field mc-field--narrow">
              <label class="mc-field__label">Adults</label>
              <input v-model.number="form.adults" class="mc-field__input" type="number" min="1" max="9" />
            </div>
            <div class="mc-field mc-field--narrow">
              <label class="mc-field__label">Min Rating</label>
              <input v-model.number="form.minRating" class="mc-field__input" type="number" min="0" max="5" step="0.1" />
            </div>
          </div>

          <!-- Row 2: Cities -->
          <div class="mc-cities-row">
            <label class="mc-field__label">Destination Cities</label>
            <div class="mc-cities">
              <span v-for="(city, i) in cities" :key="city" class="mc-city-tag">
                {{ city }}
                <button class="mc-city-tag__remove" @click="removeCity(i)" type="button">✕</button>
              </span>
              <div class="mc-city-add">
                <input
                  v-model="cityInput"
                  class="mc-field__input mc-city-input"
                  placeholder="Add city (e.g. Tokyo)"
                  @keydown.enter.prevent="addCity"
                />
                <button class="mc-btn-add" type="button" @click="addCity">+ Add</button>
              </div>
            </div>
            <p v-if="cityError" class="mc-error mc-error--inline">{{ cityError }}</p>
            <p class="mc-hint">Supported: {{ SUPPORTED_CITIES.join(', ') }}</p>
          </div>

          <!-- Actions -->
          <div class="mc-form__actions">
            <p v-if="errorMessage" class="mc-error">{{ errorMessage }}</p>
            <button class="mc-btn-search" :disabled="isLoading" @click="handleSearch">
              <span v-if="isLoading" class="spinner" />
              <span v-else>Search Packages</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Results -->
    <div class="mc-results">
      <div v-if="isLoading" class="mc-state">Searching packages across {{ cities.join(' → ') }}...</div>

      <div v-else-if="hasSearched && packages.length === 0 && !errorMessage" class="mc-state">
        No packages found. Try increasing your budget or adjusting filters.
      </div>

      <div v-if="bookingError" class="mc-state mc-state--error">{{ bookingError }}</div>

      <div v-else-if="packages.length > 0" class="mc-packages">
        <div v-for="(pkg, pi) in packages" :key="pi" class="mc-package">
          <!-- Package header -->
          <div class="mc-package__header">
            <div>
              <span class="mc-package__rank">Package {{ pi + 1 }}</span>
              <span class="mc-package__dates"> {{ pkg.departureDate }} → {{ pkg.returnDate }}</span>
              <span v-if="pkg.riskyLayoverDetected" class="mc-package__warning">⚠️ Risky layover detected</span>
            </div>
            <div class="mc-package__totals">
              <span class="mc-package__total">{{ formatCost(pkg.totalPackageCost) }}</span>
              <span class="mc-package__remaining">{{ formatCost(pkg.remainingBudget) }} remaining</span>
              <button
                class="mc-btn-book"
                :disabled="bookingPkgIndex !== null"
                @click="bookPackage(pkg, pi)"
              >
                {{ bookingPkgIndex === pi ? 'Booking…' : 'Book This Package' }}
              </button>
            </div>
          </div>

          <!-- Cost breakdown -->
          <div class="mc-cost-breakdown">
            <span class="mc-cost-item">✈️ Flights: {{ formatCost(pkg.totalFlightCost) }}</span>
            <span class="mc-cost-sep">+</span>
            <span class="mc-cost-item">🏨 Hotels: {{ formatCost(pkg.totalHotelCost) }}</span>
            <span class="mc-cost-sep">+</span>
            <span class="mc-cost-item">🎯 Activities: {{ formatCost(pkg.totalAttractionCost) }}</span>
          </div>

          <!-- Flight legs -->
          <section class="mc-section">
            <h3 class="mc-section__title">Flights — {{ formatCost(pkg.totalFlightCost) }}</h3>
            <div class="mc-flight-legs">
              <div v-for="(leg, li) in pkg.flightLegs" :key="li" class="mc-flight-leg">
                <div class="mc-flight-leg__route">{{ leg.origin }} → {{ leg.destination }}</div>
                <div class="mc-flight-leg__info">
                  {{ leg.flight.legs[0].airline }} {{ leg.flight.legs[0].flightNumber }}
                  · {{ leg.flight.legs[0].departureTime }} – {{ leg.flight.legs[0].arrivalTime }}
                  · {{ leg.flight.totalDuration }}
                </div>
                <div class="mc-flight-leg__cost">{{ formatCost(leg.flight.totalCost) }}</div>
              </div>
            </div>
          </section>

          <!-- City breakdown -->
          <section v-for="entry in pkg.cityBreakdown" :key="entry.city" class="mc-section">
            <h3 class="mc-section__title">{{ entry.city }}</h3>
            <div class="mc-city-detail">
              <div v-if="entry.hotel" class="mc-hotel-card">
                <div class="mc-hotel-card__name">{{ entry.hotel.name }}</div>
                <div class="mc-hotel-card__meta">
                  {{ '★'.repeat(entry.hotel.tags?.includes('luxury') ? 5 : entry.hotel.tags?.includes('modern') ? 4 : 3) }}
                  · Rating {{ entry.hotel.rating }}
                  · {{ entry.hotel.nights }} nights
                  · {{ formatCost(entry.hotel.totalStayCost) }}
                </div>
              </div>
              <div v-if="entry.suggestedAttractions?.length" class="mc-attractions">
                <div class="mc-attractions__header">
                  <span class="mc-attractions__label">Top things to do:</span>
                  <span class="mc-attractions__total">{{ formatCost(entry.attractionCost) }} total ({{ form.adults }} person{{ form.adults > 1 ? 's' : '' }})</span>
                </div>
                <div class="mc-attraction-list">
                  <div v-for="a in entry.suggestedAttractions" :key="a.name" class="mc-attraction-row">
                    <span class="mc-attraction-name">{{ a.name }}</span>
                    <span class="mc-attraction-price">{{ a.price > 0 ? formatCost(a.price) + '/person' : 'Free' }}</span>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mc-view {
  min-height: calc(100vh - 56px);
  background: var(--color-bg);
}

/* Search bar */
.mc-search {
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-dark) 100%);
  padding: 1.5rem 2rem;
  box-shadow: 0 4px 20px rgba(0,0,0,0.15);
}

.mc-search__inner {
  max-width: 1200px;
  margin: 0 auto;
}

.mc-search__title {
  margin: 0 0 0.15rem;
  color: #fff;
  font-size: 1.25rem;
  font-weight: 800;
}

.mc-search__sub {
  margin: 0 0 1rem;
  color: rgba(255,255,255,0.75);
  font-size: 0.85rem;
}

.mc-form__row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.mc-field {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  flex: 1;
  min-width: 120px;
}

.mc-field--narrow {
  flex: 0 0 100px;
}

.mc-field__label {
  font-size: 0.7rem;
  font-weight: 600;
  color: rgba(255,255,255,0.8);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.mc-field__input {
  height: 40px;
  padding: 0 0.75rem;
  border: 1.5px solid rgba(255,255,255,0.3);
  border-radius: 8px;
  background: rgba(255,255,255,0.12);
  color: #fff;
  font-size: 0.9rem;
  outline: none;
  box-sizing: border-box;
  width: 100%;
}

.mc-field__input--readonly {
  opacity: 0.7;
  cursor: default;
}

.mc-field__input::placeholder { color: rgba(255,255,255,0.45); }
.mc-field__input:focus {
  border-color: rgba(255,255,255,0.7);
  background: rgba(255,255,255,0.2);
}
.mc-field__input::-webkit-calendar-picker-indicator { filter: invert(1) opacity(0.7); cursor: pointer; }

/* Cities row */
.mc-cities-row {
  margin-bottom: 0.75rem;
}

.mc-cities {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.35rem;
}

.mc-city-tag {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  background: rgba(255,255,255,0.2);
  border: 1px solid rgba(255,255,255,0.4);
  border-radius: 999px;
  padding: 0.25rem 0.6rem;
  color: #fff;
  font-size: 0.85rem;
  font-weight: 600;
}

.mc-city-tag__remove {
  background: none;
  border: none;
  color: rgba(255,255,255,0.7);
  cursor: pointer;
  font-size: 0.75rem;
  padding: 0;
  line-height: 1;
}

.mc-city-add {
  display: flex;
  gap: 0.4rem;
  align-items: center;
}

.mc-city-input {
  width: 160px;
  flex: none;
}

.mc-btn-add {
  height: 40px;
  padding: 0 0.9rem;
  background: rgba(255,255,255,0.15);
  color: #fff;
  border: 1.5px solid rgba(255,255,255,0.35);
  border-radius: 8px;
  font-size: 0.88rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

.mc-hint {
  margin: 0.3rem 0 0;
  color: rgba(255,255,255,0.55);
  font-size: 0.75rem;
}

/* Actions */
.mc-form__actions {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.mc-btn-search {
  height: 42px;
  padding: 0 2rem;
  background: var(--color-accent);
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 0.95rem;
  font-weight: 700;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  transition: background 0.2s;
}

.mc-btn-search:hover:not(:disabled) { background: var(--color-accent-dark); }
.mc-btn-search:disabled { opacity: 0.7; cursor: not-allowed; }

.mc-error {
  color: #ffcdd2;
  font-size: 0.85rem;
  margin: 0;
}

.mc-error--inline {
  color: #ffcdd2;
  font-size: 0.8rem;
  margin: 0.25rem 0 0;
}

/* Results */
.mc-results {
  max-width: 1200px;
  margin: 1.5rem auto;
  padding: 0 2rem;
}

.mc-state {
  background: #fff;
  border: 1px solid var(--color-border);
  border-radius: 16px;
  padding: 2rem;
  color: var(--color-text-muted);
  text-align: center;
}

.mc-state--error {
  color: #c0392b;
  border-color: #fca5a5;
}

.mc-packages {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.mc-package {
  background: #fff;
  border: 1px solid var(--color-border);
  border-radius: 18px;
  padding: 1.5rem;
  box-shadow: 0 8px 24px rgba(26,54,93,0.06);
}

.mc-package__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1.25rem;
  flex-wrap: wrap;
}

.mc-package__rank {
  font-size: 1rem;
  font-weight: 800;
  color: var(--color-primary-dark);
}

.mc-package__dates {
  display: block;
  font-size: 0.82rem;
  color: var(--color-text-muted);
  font-weight: 600;
  margin-top: 0.15rem;
}

.mc-package__warning {
  display: block;
  margin-top: 0.15rem;
  font-size: 0.82rem;
  color: #b45309;
  font-weight: 600;
}

.mc-package__totals {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.15rem;
}

.mc-package__total {
  font-size: 1.4rem;
  font-weight: 800;
  color: var(--color-primary-dark);
}

.mc-package__remaining {
  font-size: 0.8rem;
  color: #16a34a;
  font-weight: 600;
}

.mc-btn-book {
  margin-top: 0.4rem;
  padding: 0.45rem 1.1rem;
  background: var(--color-accent);
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 0.85rem;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.2s;
  white-space: nowrap;
}
.mc-btn-book:hover:not(:disabled) { background: var(--color-accent-dark); }
.mc-btn-book:disabled { opacity: 0.7; cursor: not-allowed; }

.mc-section {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--color-border);
}

.mc-section__title {
  margin: 0 0 0.75rem;
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--color-text);
}

.mc-flight-legs {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.mc-flight-leg {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.6rem 0.75rem;
  background: #f8faff;
  border-radius: 8px;
  border: 1px solid var(--color-border);
  flex-wrap: wrap;
}

.mc-flight-leg__route {
  font-weight: 700;
  color: var(--color-primary-dark);
  min-width: 80px;
}

.mc-flight-leg__info {
  flex: 1;
  font-size: 0.88rem;
  color: var(--color-text-muted);
}

.mc-flight-leg__cost {
  font-weight: 700;
  color: var(--color-text);
}

.mc-city-detail {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.mc-hotel-card {
  padding: 0.75rem;
  background: #f8faff;
  border-radius: 10px;
  border: 1px solid var(--color-border);
}

.mc-hotel-card__name {
  font-weight: 700;
  color: var(--color-primary-dark);
  margin-bottom: 0.25rem;
}

.mc-hotel-card__meta {
  font-size: 0.85rem;
  color: var(--color-text-muted);
}

.mc-cost-breakdown {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;
  padding: 0.6rem 0.9rem;
  background: #f8faff;
  border-radius: 10px;
  border: 1px solid var(--color-border);
}

.mc-cost-item {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--color-text);
}

.mc-cost-sep {
  font-size: 0.85rem;
  color: var(--color-text-muted);
}

.mc-attractions {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.mc-attractions__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.mc-attractions__label {
  font-size: 0.8rem;
  color: var(--color-text-muted);
  font-weight: 600;
}

.mc-attractions__total {
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--color-primary);
}

.mc-attraction-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.mc-attraction-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.3rem 0.6rem;
  background: var(--color-primary-bg);
  border-radius: 6px;
}

.mc-attraction-name {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--color-primary-dark);
}

.mc-attraction-price {
  font-size: 0.78rem;
  color: var(--color-text-muted);
  font-weight: 600;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255,255,255,0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  display: inline-block;
}

@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 768px) {
  .mc-search { padding: 1rem; }
  .mc-results { padding: 0 1rem; }
  .mc-package__header { flex-direction: column; }
  .mc-package__totals { align-items: flex-start; }
}
</style>
