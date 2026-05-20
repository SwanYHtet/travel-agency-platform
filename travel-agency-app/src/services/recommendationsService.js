import axios from 'axios'
import { tenantConfig } from '../config/tenantConfig.js'

export const recommendationsService = {
  async search({ city, budget, origin, departureDate, minRating, maxHotelPrice, tag }) {
    const params = {
      city,
      budget: Number(budget),
      origin: origin || 'SFO',
      departureDate,
      minRating: Number(minRating) || 0,
    }
    // Only include optional filters when they have a value — sending null/empty
    // strings as query params causes the backend to treat them as "0" or "".
    if (maxHotelPrice) params.maxHotelPrice = Number(maxHotelPrice)
    if (tag) params.tag = tag

    const response = await axios.get('/api/phase2/recommendations', {
      params,
      headers: { 'x-tenant-id': String(tenantConfig.agentId) },
    })
    return response.data
  },
}
