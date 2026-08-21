// DRONACHARYA Store — frontend logic
// Talks to the Flask + SQLite API defined in app.py

(function () {
  "use strict";

  const API_BASE = "/api";

  /* ---------------- State ---------------- */
  let allProducts = [];
  let activeCategory = "all";
  let searchTerm = "";
  let sortMode = "newest";
  const cart = []; // { productId, cropName, unit, price, quantity }

  /* ---------------- Element refs ---------------- */
  const roleCards = document.querySelectorAll(".role-card");
  const buyerPanel = document.getElementById("buyerPanel");
  const sellerPanel = document.getElementById("sellerPanel");
  const switchButtons = document.querySelectorAll(".switch-role");

  const searchInput = document.getElementById("searchInput");
  const sortSelect = document.getElementById("sortSelect");
  const categoryChips = document.getElementById("categoryChips");
  const productGrid = document.getElementById("productGrid");

  const cartItemsEl = document.getElementById("cartItems");
  const cartTotalEl = document.getElementById("cartTotal");
  const cartTotalValueEl = document.getElementById("cartTotalValue");
  const cartCountEl = document.getElementById("cartCount");
  const checkoutForm = document.getElementById("checkoutForm");
  const checkoutStatus = document.getElementById("checkoutStatus");
  const cartHeaderBtn = document.getElementById("cartHeaderBtn");

  const sellerForm = document.getElementById("sellerForm");
  const sellerFormStatus = document.getElementById("sellerFormStatus");
  const sellerFormTitle = document.getElementById("sellerFormTitle");
  const sellerSubmitBtn = document.getElementById("sellerSubmitBtn");
  const cancelEditBtn = document.getElementById("cancelEditBtn");
  const editingProductIdEl = document.getElementById("editingProductId");
  const sellerListingsBody = document.getElementById("sellerListingsBody");

  const statActiveListings = document.getElementById("statActiveListings");
  const statTotalQuantity = document.getElementById("statTotalQuantity");
  const statOrders = document.getElementById("statOrders");

  const toast = document.getElementById("toast");

  /* ---------------- Helpers ---------------- */
  function showToast(message) {
    toast.textContent = message;
    toast.style.display = "block";
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => {
      toast.style.display = "none";
    }, 2800);
  }

  function formatCurrency(value) {
    const n = Number(value) || 0;
    return "₹" + n.toLocaleString("en-IN", { maximumFractionDigits: 2 });
  }

  function setPanel(role) {
    buyerPanel.classList.toggle("visible", role === "buyer");
    sellerPanel.classList.toggle("visible", role === "seller");
    roleCards.forEach((card) =>
      card.classList.toggle("active", card.dataset.role === role),
    );
    if (role === "buyer") fetchProducts();
    if (role === "seller") fetchProducts();
  }

  roleCards.forEach((card) => {
    card.addEventListener("click", () => setPanel(card.dataset.role));
  });

  switchButtons.forEach((btn) => {
    btn.addEventListener("click", () => setPanel(btn.dataset.target));
  });

  cartHeaderBtn.addEventListener("click", () => {
    setPanel("buyer");
    window.scrollTo({ top: buyerPanel.offsetTop - 20, behavior: "auto" });
  });

  /* ---------------- Fetch + render products (buyer + seller share the same data) ---------------- */
  async function fetchProducts() {
    try {
      const res = await fetch(`${API_BASE}/products`);
      if (!res.ok) throw new Error("Failed to load listings");
      allProducts = await res.json();
      renderBuyerGrid();
      renderSellerTable();
      renderSellerStats();
    } catch (err) {
      productGrid.innerHTML = `<div class="empty-state">Could not load listings. Please refresh the page.</div>`;
      console.error(err);
    }
  }

  function getFilteredSortedProducts() {
    let list = allProducts.filter((p) => p.status === "active");

    if (activeCategory !== "all") {
      list = list.filter((p) => p.category === activeCategory);
    }
    if (searchTerm.trim()) {
      const term = searchTerm.trim().toLowerCase();
      list = list.filter((p) => p.crop_name.toLowerCase().includes(term));
    }

    switch (sortMode) {
      case "price_low":
        list = [...list].sort((a, b) => a.price_per_unit - b.price_per_unit);
        break;
      case "price_high":
        list = [...list].sort((a, b) => b.price_per_unit - a.price_per_unit);
        break;
      case "quantity":
        list = [...list].sort((a, b) => b.quantity - a.quantity);
        break;
      default:
        list = [...list].sort((a, b) => b.id - a.id);
    }
    return list;
  }

  function renderBuyerGrid() {
    const list = getFilteredSortedProducts();

    if (list.length === 0) {
      productGrid.innerHTML = `<div class="empty-state">No listings match your search. Try a different crop or category.</div>`;
      return;
    }

    productGrid.innerHTML = list
      .map((p) => {
        const initials = p.crop_name.slice(0, 2).toUpperCase();
        const lowStock = p.quantity <= 10;
        return `
                <article class="product-card">
                    <div class="product-thumb">${initials}</div>
                    <div class="product-body">
                        <span class="product-category">${escapeHtml(p.category)}</span>
                        <h3 class="product-name">${escapeHtml(p.crop_name)}</h3>
                        <span class="product-meta">${escapeHtml(p.location)} · Sold by ${escapeHtml(p.seller_name)}</span>
                        <span class="stock-badge ${lowStock ? "low-stock" : "in-stock"}">
                            ${lowStock ? "Low stock" : "In stock"} · ${p.quantity} ${escapeHtml(p.unit)} left
                        </span>
                        <div class="product-price">${formatCurrency(p.price_per_unit)} <span>/ ${escapeHtml(p.unit)}</span></div>
                        <button class="add-cart-btn" data-id="${p.id}" type="button">Add to cart</button>
                    </div>
                </article>
            `;
      })
      .join("");

    productGrid.querySelectorAll(".add-cart-btn").forEach((btn) => {
      btn.addEventListener("click", () => addToCart(Number(btn.dataset.id)));
    });
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML;
  }

  /* ---------------- Filters ---------------- */
  searchInput.addEventListener("input", (e) => {
    searchTerm = e.target.value;
    renderBuyerGrid();
  });

  sortSelect.addEventListener("change", (e) => {
    sortMode = e.target.value;
    renderBuyerGrid();
  });

  categoryChips.addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    categoryChips
      .querySelectorAll(".chip")
      .forEach((c) => c.classList.remove("active"));
    chip.classList.add("active");
    activeCategory = chip.dataset.category;
    renderBuyerGrid();
  });

  /* ---------------- Cart ---------------- */
  function addToCart(productId) {
    const product = allProducts.find((p) => p.id === productId);
    if (!product) return;

    const existing = cart.find((c) => c.productId === productId);
    if (existing) {
      existing.quantity += 1;
    } else {
      cart.push({
        productId: product.id,
        cropName: product.crop_name,
        unit: product.unit,
        price: product.price_per_unit,
        quantity: 1,
      });
    }
    renderCart();
    showToast(`${product.crop_name} added to cart`);
  }

  function removeFromCart(productId) {
    const idx = cart.findIndex((c) => c.productId === productId);
    if (idx !== -1) cart.splice(idx, 1);
    renderCart();
  }

  function renderCart() {
    cartCountEl.textContent = String(
      cart.reduce((sum, c) => sum + c.quantity, 0),
    );

    if (cart.length === 0) {
      cartItemsEl.innerHTML = `<div class="cart-empty">Your cart is empty. Add produce from the listings to get started.</div>`;
      cartTotalEl.style.display = "none";
      checkoutForm.style.display = "none";
      return;
    }

    cartItemsEl.innerHTML = cart
      .map(
        (c) => `
            <div class="cart-item">
                <div>
                    <div class="cart-item-name">${escapeHtml(c.cropName)}</div>
                    <div class="cart-item-meta">${c.quantity} ${escapeHtml(c.unit)} × ${formatCurrency(c.price)}</div>
                </div>
                <button type="button" data-id="${c.productId}">Remove</button>
            </div>
        `,
      )
      .join("");

    cartItemsEl.querySelectorAll("button[data-id]").forEach((btn) => {
      btn.addEventListener("click", () =>
        removeFromCart(Number(btn.dataset.id)),
      );
    });

    const total = cart.reduce((sum, c) => sum + c.price * c.quantity, 0);
    cartTotalValueEl.textContent = formatCurrency(total);
    cartTotalEl.style.display = "flex";
    checkoutForm.style.display = "flex";
  }

  checkoutForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (cart.length === 0) return;

    const checkoutBtn = document.getElementById("checkoutBtn");
    checkoutBtn.disabled = true;
    checkoutStatus.textContent = "Placing your order…";
    checkoutStatus.className = "status-message";

    const payload = {
      buyer_name: document.getElementById("buyerName").value.trim(),
      buyer_contact: document.getElementById("buyerContact").value.trim(),
      buyer_address: document.getElementById("buyerAddress").value.trim(),
      items: cart.map((c) => ({
        product_id: c.productId,
        quantity: c.quantity,
      })),
    };

    try {
      const res = await fetch(`${API_BASE}/orders`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error || "Could not place the order.");
      }

      checkoutStatus.textContent = `Order placed successfully. Order ID: ${data.order_id}`;
      checkoutStatus.className = "status-message success";
      cart.length = 0;
      renderCart();
      checkoutForm.reset();
      fetchProducts(); // refresh quantities
    } catch (err) {
      checkoutStatus.textContent = err.message;
      checkoutStatus.className = "status-message error";
    } finally {
      checkoutBtn.disabled = false;
    }
  });

  /* ---------------- Seller: listings table ---------------- */
  function renderSellerTable() {
    if (allProducts.length === 0) {
      sellerListingsBody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:var(--muted); padding:24px;">No listings yet — add your first one.</td></tr>`;
      return;
    }

    sellerListingsBody.innerHTML = [...allProducts]
      .sort((a, b) => b.id - a.id)
      .map(
        (p) => `
            <tr>
                <td>${escapeHtml(p.crop_name)}</td>
                <td>${escapeHtml(p.category)}</td>
                <td>${p.quantity} ${escapeHtml(p.unit)}</td>
                <td>${formatCurrency(p.price_per_unit)}</td>
                <td>${escapeHtml(p.location)}</td>
                <td>${p.status === "active" ? "Active" : "Closed"}</td>
                <td>
                    <button class="table-action-btn" data-action="edit" data-id="${p.id}" type="button">Edit</button>
                    <button class="table-action-btn delete" data-action="delete" data-id="${p.id}" type="button">Delete</button>
                </td>
            </tr>
        `,
      )
      .join("");

    sellerListingsBody
      .querySelectorAll('[data-action="edit"]')
      .forEach((btn) => {
        btn.addEventListener("click", () => startEdit(Number(btn.dataset.id)));
      });
    sellerListingsBody
      .querySelectorAll('[data-action="delete"]')
      .forEach((btn) => {
        btn.addEventListener("click", () =>
          deleteListing(Number(btn.dataset.id)),
        );
      });
  }

  function renderSellerStats() {
    const active = allProducts.filter((p) => p.status === "active");
    statActiveListings.textContent = String(active.length);
    statTotalQuantity.textContent = active
      .reduce((sum, p) => sum + Number(p.quantity), 0)
      .toLocaleString("en-IN");
    // Order count is fetched separately, see fetchOrderCount()
    fetchOrderCount();
  }

  async function fetchOrderCount() {
    try {
      const res = await fetch(`${API_BASE}/orders`);
      if (!res.ok) return;
      const orders = await res.json();
      statOrders.textContent = String(orders.length);
    } catch (err) {
      console.error(err);
    }
  }

  function startEdit(productId) {
    const product = allProducts.find((p) => p.id === productId);
    if (!product) return;

    editingProductIdEl.value = product.id;
    document.getElementById("sellerName").value = product.seller_name;
    document.getElementById("sellerContact").value = product.seller_contact;
    document.getElementById("cropName").value = product.crop_name;
    document.getElementById("category").value = product.category;
    document.getElementById("quantity").value = product.quantity;
    document.getElementById("unit").value = product.unit;
    document.getElementById("price").value = product.price_per_unit;
    document.getElementById("harvestDate").value = product.harvest_date || "";
    document.getElementById("location").value = product.location;
    document.getElementById("description").value = product.description || "";

    sellerFormTitle.textContent = "Edit listing";
    sellerSubmitBtn.textContent = "Save changes";
    cancelEditBtn.style.display = "block";
    sellerForm.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  cancelEditBtn.addEventListener("click", () => {
    resetSellerForm();
  });

  function resetSellerForm() {
    sellerForm.reset();
    editingProductIdEl.value = "";
    sellerFormTitle.textContent = "Add a new listing";
    sellerSubmitBtn.textContent = "Publish listing";
    cancelEditBtn.style.display = "none";
    sellerFormStatus.textContent = "";
    sellerFormStatus.className = "status-message";
  }

  async function deleteListing(productId) {
    if (!confirm("Remove this listing from the marketplace?")) return;
    try {
      const res = await fetch(`${API_BASE}/products/${productId}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("Could not delete listing.");
      showToast("Listing removed.");
      fetchProducts();
    } catch (err) {
      showToast(err.message);
    }
  }

  sellerForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    sellerSubmitBtn.disabled = true;
    sellerFormStatus.textContent = "Saving…";
    sellerFormStatus.className = "status-message";

    const payload = {
      seller_name: document.getElementById("sellerName").value.trim(),
      seller_contact: document.getElementById("sellerContact").value.trim(),
      crop_name: document.getElementById("cropName").value.trim(),
      category: document.getElementById("category").value,
      quantity: Number(document.getElementById("quantity").value),
      unit: document.getElementById("unit").value,
      price_per_unit: Number(document.getElementById("price").value),
      harvest_date: document.getElementById("harvestDate").value || null,
      location: document.getElementById("location").value.trim(),
      description: document.getElementById("description").value.trim(),
    };

    const editingId = editingProductIdEl.value;

    try {
      const res = await fetch(
        editingId
          ? `${API_BASE}/products/${editingId}`
          : `${API_BASE}/products`,
        {
          method: editingId ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not save listing.");

      sellerFormStatus.textContent = editingId
        ? "Listing updated."
        : "Listing published to the marketplace.";
      sellerFormStatus.className = "status-message success";
      resetSellerForm();
      fetchProducts();
    } catch (err) {
      sellerFormStatus.textContent = err.message;
      sellerFormStatus.className = "status-message error";
    } finally {
      sellerSubmitBtn.disabled = false;
    }
  });

  /* ---------------- Init ---------------- */
  fetchProducts();
})();
