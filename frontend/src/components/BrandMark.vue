<script setup lang="ts">
defineProps({ large: Boolean });
</script>

<template>
  <span class="brand-mark" :class="{ large }">
    <span />
  </span>
</template>

<style scoped>
.brand-mark {
  width: 2rem;
  height: 2rem;
  border: 1.3px solid #c69a60;
  border-radius: 50%;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.brand-mark span {
  width: 1.375rem;
  height: 1.375rem;
  border-radius: 50%;
  background: linear-gradient(145deg, #f1d19b, #be8b42);
}
.brand-mark.large {
  width: 3.375rem;
  height: 3.375rem;
}
.brand-mark.large span {
  width: 2.25rem;
  height: 2.25rem;
}
</style>
