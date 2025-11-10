import { create } from 'zustand'

export const useFeatureStore = create((set) => ({
  currentFeature: null,
  features: [],
  isLoading: false,
  
  setCurrentFeature: (feature) => set({ currentFeature: feature }),
  setFeatures: (features) => set({ features }),
  setLoading: (isLoading) => set({ isLoading }),
  
  addFeature: (feature) => set((state) => ({
    features: [feature, ...state.features]
  })),
  
  updateFeature: (id, updates) => set((state) => ({
    features: state.features.map(f => 
      f.id === id ? { ...f, ...updates } : f
    ),
    currentFeature: state.currentFeature?.id === id 
      ? { ...state.currentFeature, ...updates }
      : state.currentFeature
  })),
  
  reset: () => set({
    currentFeature: null,
    features: [],
    isLoading: false
  })
}))

