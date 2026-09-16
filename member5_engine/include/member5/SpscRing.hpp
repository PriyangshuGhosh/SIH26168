#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <optional>
#include <type_traits>

namespace sih26168::member5 {

/* Single-producer / single-consumer lock-free ring. Capacity must be a power of two. */
template <typename T, std::size_t Capacity>
class SpscRing {
    static_assert((Capacity & (Capacity - 1)) == 0, "Capacity must be a power of two");
    static_assert(std::is_trivially_copyable_v<T>, "T must be trivially copyable");

public:
    bool push(const T& item) {
        const std::size_t w = write_.load(std::memory_order_relaxed);
        const std::size_t r = read_.load(std::memory_order_acquire);
        if (((w + 1) & kMask) == (r & kMask)) {
            return false;
        }
        buf_[w & kMask] = item;
        write_.store(w + 1, std::memory_order_release);
        return true;
    }

    std::optional<T> pop() {
        const std::size_t r = read_.load(std::memory_order_relaxed);
        const std::size_t w = write_.load(std::memory_order_acquire);
        if (r == w) {
            return std::nullopt;
        }
        T item = buf_[r & kMask];
        read_.store(r + 1, std::memory_order_release);
        return item;
    }

    std::size_t size_approx() const {
        const std::size_t w = write_.load(std::memory_order_acquire);
        const std::size_t r = read_.load(std::memory_order_acquire);
        return w - r;
    }

    void clear() {
        const std::size_t w = write_.load(std::memory_order_relaxed);
        read_.store(w, std::memory_order_release);
    }

private:
    static constexpr std::size_t kMask = Capacity - 1;
    std::array<T, Capacity> buf_{};
    alignas(64) std::atomic<std::size_t> write_{0};
    alignas(64) std::atomic<std::size_t> read_{0};
};

}  // namespace sih26168::member5
