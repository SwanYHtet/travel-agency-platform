import axios from 'axios'
import { tenantConfig } from '../config/tenantConfig.js'

export const multiCityService = {
  async searchPackages({ cities, originIata, returnIata, departureDate, budget, nightsPerCity, adults, minRating, maxHotelPricePerNight }) {
    const body = {
      cities,
      origin_iata: originIata,
      return_iata: returnIata,
      departure_date: departureDate,
      budget: Number(budget),
      nights_per_city: Number(nightsPerCity) || 3,
      adults: Number(adults) || 1,
      minRating: Number(minRating) || 0,
    }
    // Pydantic v2 rejects null for a plain `float` field (needs Optional[float]).
    // Omitting the key entirely avoids a 422 validation error when the user leaves the field blank.
    if (maxHotelPricePerNight) {
      body.maxHotelPricePerNight = Number(maxHotelPricePerNight)
    }
    const response = await axios.post(
      '/api/phase2/packages/multi-city',
      body,
      {
        headers: { 'x-tenant-id': String(tenantConfig.agentId) },
      }
    )
    return response.data
  },
}
