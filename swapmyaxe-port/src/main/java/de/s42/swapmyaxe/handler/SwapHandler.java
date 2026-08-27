package de.s42.swapmyaxe.handler;

import de.s42.swapmyaxe.SwapMyAxe;
import de.s42.swapmyaxe.config.Config;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.event.player.AttackBlockCallback;
import net.fabricmc.fabric.api.event.player.AttackEntityCallback;
import net.minecraft.client.Minecraft;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.item.AxeItem;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.phys.BlockHitResult;

public class SwapHandler {

    private static int pendingSwapTicks = -1;
    private static int pendingRestoreTicks = -1;
    private static int axeSlot = -1;
    private static int targetSlot = -1;
    private static Entity lastTargetEntity = null;
    private static BlockHitResult lastBlockHitResult = null;

    private SwapHandler() {}

    public static void register() {
        AttackEntityCallback.EVENT.register((player, world, hand, entity, hitResult) -> {
            if (!world.isClientSide()) return InteractionResult.PASS;
            handleAttack(entity, null);
            return InteractionResult.PASS;
        });

        AttackBlockCallback.EVENT.register((player, world, hand, pos, direction) -> {
            if (!world.isClientSide()) return InteractionResult.PASS;
            BlockHitResult bhr = new BlockHitResult(player.getLookAngle(), direction, pos, false);
            handleAttack(null, bhr);
            return InteractionResult.PASS;
        });

        ClientTickEvents.END_CLIENT_TICK.register(client -> {
            if (pendingSwapTicks >= 0) {
                if (pendingSwapTicks == 0) executeSwapHit(client);
                else pendingSwapTicks--;
            }

            if (pendingRestoreTicks >= 0) {
                if (pendingRestoreTicks == 0) {
                    if (client.player != null && axeSlot != -1) {
                        client.player.getInventory().setSelectedSlot(axeSlot);
                    }
                    axeSlot = -1;
                    pendingRestoreTicks = -1;
                } else {
                    pendingRestoreTicks--;
                }
            }
        });
    }

    private static void handleAttack(Entity targetEntity, BlockHitResult blockHit) {
        Config cfg = SwapMyAxe.CONFIG;
        if (cfg == null || !cfg.enabled) return;

        Minecraft client = Minecraft.getInstance();
        if (client.player == null) return;

        Inventory inv = client.player.getInventory();
        int currentSlot = inv.getSelectedSlot();

        ItemStack held = client.player.getMainHandItem();
        if (!(held.getItem() instanceof AxeItem)) return;
        if (pendingSwapTicks >= 0 || pendingRestoreTicks >= 0) return;

        int resolved = resolveTargetSlot(inv, cfg, currentSlot);
        if (resolved == -1 || resolved == currentSlot) return;

        axeSlot = currentSlot;
        targetSlot = resolved;
        lastTargetEntity = targetEntity;
        lastBlockHitResult = blockHit;
        pendingSwapTicks = Math.max(0, cfg.swapDelayTicks);
    }

    private static void executeSwapHit(Minecraft client) {
        pendingSwapTicks = -1;
        if (client.player == null) {
            resetPendingAttack();
            return;
        }

        Config cfg = SwapMyAxe.CONFIG;
        if (cfg == null || targetSlot < 0 || targetSlot > 8) {
            resetPendingAttack();
            return;
        }

        client.player.getInventory().setSelectedSlot(targetSlot);

        if (cfg.doubleHit && client.gameMode != null) {
            if (lastTargetEntity != null && !lastTargetEntity.isRemoved()) {
                client.gameMode.attack(client.player, lastTargetEntity);
            } else if (lastBlockHitResult != null) {
                client.gameMode.startDestroyBlock(lastBlockHitResult.getBlockPos(), lastBlockHitResult.getDirection());
            }
            client.player.swing(InteractionHand.MAIN_HAND);
        }

        lastTargetEntity = null;
        lastBlockHitResult = null;

        if (cfg.restoreToAxe && axeSlot >= 0 && axeSlot <= 8) {
            pendingRestoreTicks = 1;
        } else {
            axeSlot = -1;
            pendingRestoreTicks = -1;
        }
        targetSlot = -1;
    }

    private static void resetPendingAttack() {
        lastTargetEntity = null;
        lastBlockHitResult = null;
        pendingSwapTicks = -1;
        pendingRestoreTicks = -1;
        axeSlot = -1;
        targetSlot = -1;
    }

    private static int resolveTargetSlot(Inventory inv, Config cfg, int currentSlot) {
        if (cfg.swapMode == Config.SwapMode.SLOT) {
            return Math.max(0, Math.min(8, cfg.targetSlot));
        }

        ResourceLocation targetId;
        try {
            targetId = ResourceLocation.parse(cfg.targetItem);
        } catch (RuntimeException e) {
            SwapMyAxe.LOGGER.warn("Invalid target item id: {}", cfg.targetItem);
            return -1;
        }

        for (int i = 0; i < 9; i++) {
            if (i == currentSlot) continue;
            ItemStack stack = inv.getItem(i);
            if (stack.isEmpty()) continue;
            ResourceLocation stackId = BuiltInRegistries.ITEM.getKey(stack.getItem());
            if (targetId.equals(stackId)) return i;
        }
        return -1;
    }
}
