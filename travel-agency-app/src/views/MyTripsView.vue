<script setup>
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'
import { tenantConfig } from '../config/tenantConfig.js'
import { bookingService } from '../services/bookingService.js'
import { useAuth } from '../composables/useAuth.js'

const { userId, userEmail } = useAuth()

const isLoading = ref(true)
const errorMessage = ref('')
const trips = ref([])
const cancellingId = ref(null)
const confirmingId = ref(null)

// The professor's API has no status field on bookings.
// We persist Pending/Confirmed in localStorage so the badge survives page refreshes.
const STATUS_KEY = 'booking_statuses'
const ATTRACTION_KEY = 'booking_attractions'

function loadBookingAttractions(bookingId) {
  try {
    const stored = JSON.parse(localStorage.getItem(ATTRACTION_KEY) || '{}')
    return stored[bookingId] || null
  } catch { return null }
}

function loadStatuses() {
  try { return JSON.parse(localStorage.getItem(STATUS_KEY) || '{}') } catch { return {} }
}

function saveStatus(bookingId, status) {
  const statuses = loadStatuses()
  statuses[bookingId] = status
  localStorage.setItem(STATUS_KEY, JSON.stringify(statuses))
}

function getStatus(bookingId) {
  return loadStatuses()[bookingId] || 'Pending'
}

function formatDate(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value || 'N/A'
  return date.toLocaleDateString('en-GB', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

const tripCountLabel = computed(() => {
  const tripCount = trips.value.length
  return tripCount === 1 ? '1 saved trip' : `${tripCount} saved trips`
})

async function loadTrips() {
  isLoading.value = true
  errorMessage.value = ''

  try {
    const raw = await bookingService.listBookings({
      userId: userId.value,
      agentId: tenantConfig.agentId,
    })
    trips.value = raw.map(t => ({
      ...t,
      _status: getStatus(t.bookingId),
      _attractions: loadBookingAttractions(t.bookingId),
    }))
  } catch (error) {
    errorMessage.value = error.message || 'Unable to load saved trips.'
    trips.value = []
  } finally {
    isLoading.value = false
  }
}

async function confirmTrip(bookingId) {
  confirmingId.value = bookingId
  try {
    // The Phase 2 booking ID may differ from the professor's booking ID, so this
    // PATCH can return 404. We fire-and-forget it (.catch(() => {})) and rely on
    // localStorage as the source of truth for the confirmed state.
    await axios.patch(
      `/api/phase2/bookings/${bookingId}/status`,
      { status: 'Confirmed' },
      { headers: { 'x-tenant-id': String(tenantConfig.agentId) } }
    ).catch(() => {})
    saveStatus(bookingId, 'Confirmed')
    trips.value = trips.value.map(t =>
      t.bookingId === bookingId ? { ...t, _status: 'Confirmed' } : t
    )
  } finally {
    confirmingId.value = null
  }
}

async function cancelTrip(bookingId) {
  if (!confirm('Cancel this booking? This cannot be undone.')) return
  cancellingId.value = bookingId
  try {
    // Phase 2 cancel is best-effort; professor's DELETE is the authoritative removal.
    await axios.post(
      `/api/phase2/bookings/${bookingId}/cancel`,
      {},
      { headers: { 'x-tenant-id': String(tenantConfig.agentId) } }
    ).catch(() => {})
    await bookingService.cancelBooking(bookingId)
    trips.value = trips.value.filter(t => t.bookingId !== bookingId)
    // Clean up the localStorage entry so the status badge doesn't reappear.
    const statuses = loadStatuses()
    delete statuses[bookingId]
    localStorage.setItem(STATUS_KEY, JSON.stringify(statuses))
  } catch (err) {
    alert(err.message || 'Failed to cancel booking.')
  } finally {
    cancellingId.value = null
  }
}

onMounted(() => {
  loadTrips()
})
</script>

<template>
  <div class="my-trips-view">
    <div class="my-trips-view__hero">
      <div>
        <p class="my-trips-view__eyebrow">Agent {{ tenantConfig.agentId }}</p>
        <h1 class="my-trips-view__title">My Trips</h1>
        <p class="my-trips-view__sub">
          Saved trips for {{ userEmail || `User ${userId}` }} with {{ tenantConfig.brandName }}.
        </p>
      </div>
      <div class="my-trips-view__summary">{{ tripCountLabel }}</div>
    </div>

    <div v-if="isLoading" class="state-card">Loading saved trips...</div>
    <div v-else-if="errorMessage" class="state-card state-card--error">{{ errorMessage }}</div>
    <div v-else-if="trips.length === 0" class="state-card">No saved trips found for this user and agent.</div>

    <div v-else class="trips-list">
      <article v-for="trip in trips" :key="trip.bookingId" class="trip-card">
        <div class="trip-card__header">
          <div>
            <p class="trip-card__meta">Booking #{{ trip.bookingId }}</p>
            <h2 class="trip-card__title">{{ formatDate(trip.startDate) }} to {{ formatDate(trip.endDate) }}</h2>
          </div>
          <div class="trip-card__actions">
            <div class="trip-card__pill">{{ trip.flightReservations.length }} flights · {{ trip.hotelReservations.length }} hotels</div>
            <span class="trip-card__status" :class="`trip-card__status--${(trip._status || 'Pending').toLowerCase()}`">
              {{ trip._status || 'Pending' }}
            </span>
            <div class="trip-card__btns">
              <button
                v-if="trip._status !== 'Confirmed'"
                class="trip-card__confirm"
                :disabled="confirmingId === trip.bookingId"
                @click="confirmTrip(trip.bookingId)"
              >
                {{ confirmingId === trip.bookingId ? 'Confirming…' : 'Confirm' }}
              </button>
              <button
                class="trip-card__cancel"
                :disabled="cancellingId === trip.bookingId"
                @click="cancelTrip(trip.bookingId)"
              >
                {{ cancellingId === trip.bookingId ? 'Cancelling…' : 'Cancel' }}
              </button>
            </div>
          </div>
        </div>

        <section class="trip-section">
          <h3 class="trip-section__title">Flight Details</h3>
          <p v-if="trip.flightReservations.length === 0" class="trip-section__empty">No flights saved for this trip.</p>
          <div v-else class="reservation-grid">
            <div v-for="flight in trip.flightReservations" :key="`${trip.bookingId}-${flight.Reservation_No}`" class="reservation-card">
              <div class="reservation-card__title">Flight Reservation</div>
              <div><strong>Airline code:</strong> {{ flight.Airline_Code || 'N/A' }}</div>
              <div><strong>Flight number:</strong> {{ flight.Flight_Number || 'N/A' }}</div>
              <div>{{ flight.Origin_Airport_Code }} to {{ flight.Destination_Airport_Code }}</div>
              <div>Departure: {{ formatDate(flight.Departure_Date) }} {{ flight.Departure_Time }}</div>
              <div>Arrival: {{ formatDate(flight.Arrive_Date) }} {{ flight.Arrive_Time }}</div>
              <div>Rate: ${{ Number(flight.Rate || 0).toLocaleString() }}</div>
            </div>
          </div>
        </section>

        <section class="trip-section">
          <h3 class="trip-section__title">Hotel Details</h3>
          <p v-if="trip.hotelReservations.length === 0" class="trip-section__empty">No hotel saved for this trip.</p>
          <div v-else class="reservation-grid">
            <div v-for="hotel in trip.hotelReservations" :key="`${trip.bookingId}-${hotel.Reservation_No}`" class="reservation-card">
              <div class="reservation-card__title">Hotel Reservation</div>
              <div><strong>Hotal Name:</strong> {{ hotel.Hotel_Name || 'Hotel name unavailable' }}</div>
              <div>Check in: {{ formatDate(hotel.Check_In_Date) }} {{ hotel.Check_In_Time }}</div>
              <div>Check out: {{ formatDate(hotel.Check_Out_Date) }} {{ hotel.Check_Out_Time }}</div>
              <div>Rate: ${{ Number(hotel.Rate || 0).toLocaleString() }}</div>
            </div>
          </div>
        </section>

        <section v-if="trip._attractions" class="trip-section">
          <h3 class="trip-section__title">Activity Details</h3>
          <div class="reservation-grid">
            <div v-for="entry in trip._attractions" :key="entry.city" class="reservation-card">
              <div class="reservation-card__title">{{ entry.city }}</div>
              <div v-for="a in entry.attractions" :key="a.name" class="activity-row">
                <span>{{ a.name }}</span>
                <span class="activity-price">{{ a.price > 0 ? '$' + a.price + '/person' : 'Free' }}</span>
              </div>
              <div class="activity-total">Total: ${{ Number(entry.attractionCost || 0).toLocaleString() }}</div>
            </div>
          </div>
        </section>
      </article>
    </div>
  </div>
</template>

<style scoped>
.my-trips-view {
  min-height: calc(100vh - 56px);
  background: var(--color-bg);
  padding: 2rem;
}

.my-trips-view__hero {
  max-width: 1200px;
  margin: 0 auto 1.5rem;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
}

.my-trips-view__eyebrow {
  margin: 0 0 0.35rem;
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-accent-dark);
}

.my-trips-view__title {
  margin: 0;
  font-size: 2rem;
  color: var(--color-primary-dark);
}

.my-trips-view__sub {
  margin: 0.5rem 0 0;
  color: var(--color-text-muted);
}

.my-trips-view__summary {
  padding: 0.6rem 0.9rem;
  border-radius: 999px;
  background: #fff;
  border: 1px solid var(--color-border);
  color: var(--color-text);
  font-weight: 700;
}

.state-card {
  max-width: 1200px;
  margin: 0 auto;
  background: #fff;
  border: 1px solid var(--color-border);
  border-radius: 16px;
  padding: 2rem;
  color: var(--color-text-muted);
}

.state-card--error {
  color: #c0392b;
}

.trips-list {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.trip-card {
  background: #fff;
  border: 1px solid var(--color-border);
  border-radius: 18px;
  padding: 1.5rem;
  box-shadow: 0 10px 24px rgba(26, 54, 93, 0.06);
}

.trip-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.25rem;
}

.trip-card__meta {
  margin: 0 0 0.35rem;
  font-size: 0.8rem;
  color: var(--color-text-muted);
}

.trip-card__title {
  margin: 0;
  color: var(--color-primary-dark);
  font-size: 1.2rem;
}

.trip-card__actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.4rem;
}

.trip-card__status {
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.trip-card__status--pending {
  background: #fef9c3;
  color: #854d0e;
}

.trip-card__status--confirmed {
  background: #dcfce7;
  color: #166534;
}

.trip-card__btns {
  display: flex;
  gap: 0.4rem;
}

.trip-card__confirm {
  padding: 0.35rem 0.75rem;
  border-radius: 8px;
  border: 1px solid #86efac;
  background: #f0fdf4;
  color: #166534;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}

.trip-card__confirm:hover:not(:disabled) {
  background: #dcfce7;
}

.trip-card__confirm:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.trip-card__cancel {
  padding: 0.35rem 0.75rem;
  border-radius: 8px;
  border: 1px solid #fca5a5;
  background: #fff5f5;
  color: #dc2626;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}

.trip-card__cancel:hover:not(:disabled) {
  background: #fee2e2;
}

.trip-card__cancel:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.trip-card__pill {
  padding: 0.45rem 0.75rem;
  border-radius: 999px;
  background: var(--color-primary-bg);
  color: var(--color-primary-dark);
  font-size: 0.85rem;
  font-weight: 700;
  white-space: nowrap;
}

.trip-section + .trip-section {
  margin-top: 1.25rem;
}

.trip-section__title {
  margin: 0 0 0.75rem;
  color: var(--color-text);
  font-size: 1rem;
}

.trip-section__empty {
  margin: 0;
  color: var(--color-text-muted);
}

.reservation-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 0.75rem;
}

.reservation-card {
  border: 1px solid var(--color-border);
  border-radius: 14px;
  padding: 1rem;
  background: #fcfdff;
  color: var(--color-text);
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.reservation-card__title {
  font-weight: 700;
  color: var(--color-primary-dark);
}

.activity-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.88rem;
}

.activity-price {
  color: var(--color-text-muted);
  font-weight: 600;
}

.activity-total {
  font-weight: 700;
  color: var(--color-primary);
  margin-top: 0.25rem;
  font-size: 0.9rem;
}

@media (max-width: 768px) {
  .my-trips-view {
    padding: 1rem;
  }

  .my-trips-view__hero,
  .trip-card__header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>